#include "esphome/core/defines.h"
#if defined(USE_MATTER) && defined(USE_MATTER_SWITCH)

#include "matter_component.h"
#include "esphome/core/application.h"
#include <app/clusters/switch-server/SwitchCluster.h>
#include <platform/CHIPDeviceLayer.h>
#include <new>

namespace esphome::matter {
namespace {
static const char *const TAG = "matter.switch";
static constexpr uint32_t LONG_PRESS_MS = 800;
static constexpr uint32_t MULTI_PRESS_MS = 350;
static constexpr uint8_t MULTI_PRESS_MAX = 2;

enum class SwitchEvent { POSITION, INITIAL, SHORT_RELEASE, LONG, LONG_RELEASE, ONGOING, COMPLETE };
struct SwitchUpdate {
  uint16_t endpoint;
  bool pressed;
  SwitchEvent event;
  uint8_t count;
};

void publish_on_matter_thread(intptr_t arg) {
  auto *update = reinterpret_cast<SwitchUpdate *>(arg);
  auto *base = esp_matter::data_model::provider::get_instance().registry().Get(
      {update->endpoint, chip::app::Clusters::Switch::Id});
  if (base == nullptr) {
    ESP_LOGE(TAG, "Switch cluster missing on endpoint %u", update->endpoint);
    delete update;
    return;
  }
  auto *cluster = static_cast<chip::app::Clusters::SwitchCluster *>(base);
  CHIP_ERROR err = cluster->SetCurrentPosition(update->pressed ? 1 : 0);
  if (err != CHIP_NO_ERROR) {
    ESP_LOGE(TAG, "Failed to update switch position: %s", err.AsString());
  } else if (update->event != SwitchEvent::POSITION) {
    std::optional<chip::EventNumber> event;
    const char *name = "";
    switch (update->event) {
      case SwitchEvent::INITIAL: event = cluster->OnInitialPress(1); name = "InitialPress"; break;
      case SwitchEvent::SHORT_RELEASE: event = cluster->OnShortRelease(1); name = "ShortRelease"; break;
      case SwitchEvent::LONG: event = cluster->OnLongPress(1); name = "LongPress"; break;
      case SwitchEvent::LONG_RELEASE: event = cluster->OnLongRelease(1); name = "LongRelease"; break;
      case SwitchEvent::ONGOING: event = cluster->OnMultiPressOngoing(1, update->count); name = "MultiPressOngoing"; break;
      case SwitchEvent::COMPLETE: event = cluster->OnMultiPressComplete(1, update->count); name = "MultiPressComplete"; break;
      default: break;
    }
    if (event.has_value())
      ESP_LOGD(TAG, "Endpoint %u: %s (count=%u)", update->endpoint, name, update->count);
    else
      ESP_LOGW(TAG, "Could not emit %s on endpoint %u", name, update->endpoint);
  }
  delete update;
}

class MatterSwitchMapping : public MatterEndpointMappingBase {
public:
  MatterSwitchMapping(MatterComponent *owner, binary_sensor::BinarySensor *sensor, uint16_t endpoint)
      : MatterEndpointMappingBase(endpoint), owner_(owner), sensor_(sensor) {}

  void register_callbacks() override {
    if (this->sensor_->has_state())
      this->on_state_(this->sensor_->state);
    this->sensor_->add_on_state_callback([this](bool state) { this->on_state_(state); });
  }

private:
  uint32_t long_timer_() const { return 0x10000u + this->endpoint_id_; }
  uint32_t multi_timer_() const { return 0x20000u + this->endpoint_id_; }

  bool publish_(bool pressed, SwitchEvent event, uint8_t count = 0) {
    auto *update = new (std::nothrow) SwitchUpdate{this->endpoint_id_, pressed, event, count};
    if (update == nullptr) {
      ESP_LOGW(TAG, "No memory for switch event");
      return false;
    }
    CHIP_ERROR err = chip::DeviceLayer::PlatformMgr().ScheduleWork(
        publish_on_matter_thread, reinterpret_cast<intptr_t>(update));
    if (err != CHIP_NO_ERROR) {
      delete update;
      ESP_LOGW(TAG, "Failed to schedule switch event: %s", err.AsString());
      return false;
    }
    return true;
  }

  void on_state_(bool pressed) {
    if (!this->initialized_) {
      // Synchronize without inventing a gesture, including a button held at boot.
      if (this->publish_(pressed, SwitchEvent::POSITION)) {
        this->initialized_ = true;
        this->last_state_ = pressed;
      }
      return;
    }
    if (this->last_state_ == pressed)
      return;
    this->last_state_ = pressed;
    if (pressed) {
      App.scheduler.cancel_timeout(this->owner_, this->multi_timer_());
      this->active_ = this->publish_(true, SwitchEvent::INITIAL);
      this->long_ = false;
      if (!this->active_) {
        this->count_ = 0;
        return;
      }
      // Saturate above the advertised maximum: an overflow sequence reports 0.
      if (this->count_ < MULTI_PRESS_MAX + 1)
        ++this->count_;
      if (this->count_ > 1) {
        this->publish_(true, SwitchEvent::ONGOING, this->count_);
      } else {
        App.scheduler.set_timeout(this->owner_, this->long_timer_(), LONG_PRESS_MS, [this]() {
          if (this->active_ && this->last_state_)
            this->long_ = this->publish_(true, SwitchEvent::LONG);
        });
      }
    } else {
      App.scheduler.cancel_timeout(this->owner_, this->long_timer_());
      if (!this->active_) {
        this->publish_(false, SwitchEvent::POSITION);
        return;
      }
      this->active_ = false;
      if (!this->publish_(false, this->long_ ? SwitchEvent::LONG_RELEASE : SwitchEvent::SHORT_RELEASE)) {
        this->count_ = 0;
        return;
      }
      if (this->long_) {
        this->count_ = 0;
      } else {
        App.scheduler.set_timeout(this->owner_, this->multi_timer_(), MULTI_PRESS_MS, [this]() {
          this->publish_(false, SwitchEvent::COMPLETE,
                         this->count_ <= MULTI_PRESS_MAX ? this->count_ : 0);
          this->count_ = 0;
        });
      }
    }
  }

  MatterComponent *owner_;
  binary_sensor::BinarySensor *sensor_;
  bool initialized_{false};
  bool last_state_{false};
  bool active_{false};
  bool long_{false};
  uint8_t count_{0};
};
} // namespace

void MatterComponent::map_switch_to_endpoint(binary_sensor::BinarySensor *sensor,
                                             uint16_t endpoint_id) {
  this->mappings_.push_back(new MatterSwitchMapping(this, sensor, endpoint_id));
}
} // namespace esphome::matter
#endif // USE_MATTER && USE_MATTER_SWITCH
