"""Exercise the real switch mapping with a queued Matter thread and SDK doubles."""
from pathlib import Path
import subprocess
import tempfile
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SwitchEvents(unittest.TestCase):
    def test_codegen_creates_only_requested_clusters(self):
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            config = yaml.safe_load((ROOT / "tests/configs/esp32-ethernet.yaml").read_text())
            config["external_components"][0]["source"] = str(ROOT / "components")
            config["esphome"]["build_path"] = str(Path(tmp) / "build")
            path = Path(tmp) / "button.yaml"
            path.write_text(yaml.safe_dump(config))
            result = subprocess.run(
                [sys.executable, "-m", "esphome", "compile", str(path), "--only-generate"],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            generated = (Path(tmp) / "build/src/main.cpp").read_text()
            self.assertIn("config.switch_cluster.feature_flags", generated)
            self.assertIn("momentary_switch_release::get_id()", generated)
            self.assertIn("map_switch_to_endpoint", generated)
            self.assertNotIn("esp_matter::cluster::fixed_label", generated)
            self.assertNotIn("esp_matter::cluster::user_label", generated)

    def test_unsupported_features_rejected(self):
        import yaml
        for feature in ("LatchingSwitch", "ActionSwitch"):
            with self.subTest(feature=feature), tempfile.TemporaryDirectory() as tmp:
                config = yaml.safe_load((ROOT / "tests/configs/esp32-ethernet.yaml").read_text())
                config["external_components"][0]["source"] = str(ROOT / "components")
                config["matter"]["endpoints"][2]["generic_switch"]["features"] = [feature]
                path = Path(tmp) / "invalid.yaml"
                path.write_text(yaml.safe_dump(config))
                result = subprocess.run([sys.executable, "-m", "esphome", "config", str(path)],
                                        capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("supports only momentary button", result.stdout + result.stderr)

    def test_edges_startup_and_scheduling(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('esphome/core/defines.h', 'esphome/core/application.h', 'platform/CHIPDeviceLayer.h',
                         'app/clusters/switch-server/SwitchCluster.h'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('#pragma once\n')
            (root / 'matter_switch.cpp').write_text(
                (ROOT / 'components/matter/matter_switch.cpp').read_text())
            (root / 'matter_component.h').write_text(r'''
#pragma once
#include <cassert>
#include <cstdint>
#include <functional>
#include <optional>
#include <utility>
#include <vector>
#include <map>
#define ESP_LOGE(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
#define ESP_LOGD(...) ((void)0)
struct CHIP_ERROR { int code; const char *AsString() { return "error"; } };
inline bool operator!=(CHIP_ERROR a, CHIP_ERROR b) { return a.code != b.code; }
constexpr CHIP_ERROR CHIP_NO_ERROR{0};
std::vector<int> events;
int position = 0;
bool fail_schedule = false;
std::vector<std::pair<void(*)(intptr_t), intptr_t>> work;
namespace chip { using EventNumber = int; }
namespace chip::app::Clusters {
namespace Switch { constexpr uint32_t Id = 59; }
struct SwitchCluster {
 CHIP_ERROR SetCurrentPosition(uint8_t p) { position = p; return CHIP_NO_ERROR; }
 std::optional<int> OnInitialPress(uint8_t p) { assert(p == 1 && position == 1); events.push_back(1); return 1; }
 std::optional<int> OnShortRelease(uint8_t p) { assert(p == 1 && position == 0); events.push_back(0); return 2; }
 std::optional<int> OnLongPress(uint8_t p) { assert(p == 1 && position == 1); events.push_back(2); return 3; }
 std::optional<int> OnLongRelease(uint8_t p) { assert(p == 1 && position == 0); events.push_back(3); return 4; }
 std::optional<int> OnMultiPressOngoing(uint8_t p, uint8_t n) { assert(p == 1 && position == 1); events.push_back(10+n); return 5; }
 std::optional<int> OnMultiPressComplete(uint8_t p, uint8_t n) { assert(p == 1 && position == 0); events.push_back(20+n); return 6; }
};
}
namespace chip::DeviceLayer {
struct Manager {
 CHIP_ERROR ScheduleWork(void(*f)(intptr_t), intptr_t arg) {
  if (fail_schedule) return CHIP_ERROR{1};
  work.emplace_back(f, arg); return CHIP_NO_ERROR;
 }
};
inline Manager &PlatformMgr() { static Manager m; return m; }
}
namespace esp_matter::data_model::provider {
struct Registry {
 chip::app::Clusters::SwitchCluster *Get(std::pair<uint16_t,uint32_t>) {
  static chip::app::Clusters::SwitchCluster c; return &c;
 }
};
struct Provider { Registry &registry() { static Registry r; return r; } };
inline Provider &get_instance() { static Provider p; return p; }
}
namespace esphome::binary_sensor {
struct BinarySensor {
 bool state = false, valid = false;
 std::function<void(bool)> cb;
 bool has_state() { return valid; }
 void add_on_state_callback(std::function<void(bool)> f) { cb = f; }
 void emit(bool v) { state = v; valid = true; cb(v); }
};
}
namespace esphome {
uint64_t now = 0;
struct Scheduler {
 struct Timer { uint64_t when; std::function<void()> f; };
 std::map<std::pair<void*, uint32_t>, Timer> timers;
 void set_timeout(void *owner, uint32_t id, uint32_t delay, std::function<void()> f) { timers[{owner,id}]={now+delay,f}; }
 bool cancel_timeout(void *owner, uint32_t id) { return timers.erase({owner,id}); }
 void advance(uint32_t ms) {
  now += ms;
  for (;;) {
   auto it = timers.begin();
   while (it != timers.end() && it->second.when > now) ++it;
   if (it == timers.end()) break;
   auto f = it->second.f; timers.erase(it); f();
  }
 }
};
struct Application { Scheduler scheduler; } App;
}
namespace esphome::matter {
struct MatterEndpointMappingBase {
 uint16_t endpoint_id_;
 explicit MatterEndpointMappingBase(uint16_t ep):endpoint_id_(ep) {}
 virtual ~MatterEndpointMappingBase() = default;
 virtual void register_callbacks() = 0;
};
struct MatterComponent {
 std::vector<MatterEndpointMappingBase*> mappings_;
 void map_switch_to_endpoint(binary_sensor::BinarySensor*, uint16_t);
};
}
''')
            (root / 'main.cpp').write_text(r'''
#define USE_MATTER
#define USE_MATTER_SWITCH
#include "matter_switch.cpp"
void drain() {
 auto pending = std::move(work); work.clear();
 for (auto [f, arg] : pending) f(arg);
}
void advance(uint32_t ms) { esphome::App.scheduler.advance(ms); drain(); }
void expect(std::vector<int> want) { drain(); assert(events == want); events.clear(); }
int main() {
 using esphome::matter::MatterSwitchMapping;
 esphome::matter::MatterComponent owner;
 esphome::binary_sensor::BinarySensor sensor;
 MatterSwitchMapping mapping(&owner, &sensor, 2);
 mapping.register_callbacks();
 sensor.emit(false); expect({});
 // One click waits for the complete window; duplicate edges are ignored.
 sensor.emit(true); sensor.emit(true); sensor.emit(false);
 assert(events.empty()); // SDK access is queued on the Matter thread.
 expect({1,0}); advance(349); expect({}); advance(1); expect({21});
 // Double click: one completion with count 2, no single completion.
 sensor.emit(true); sensor.emit(false); advance(100);
 sensor.emit(true); sensor.emit(false); expect({1,0,1,12,0});
 advance(350); expect({22});
 // Long hold produces exactly one LongPress and LongRelease, no completion.
 sensor.emit(true); advance(799); expect({1});
 advance(1); expect({2}); advance(2000); expect({});
 sensor.emit(false); expect({3}); advance(350); expect({});
 // Long is recognized only at the start of a multi-press sequence.
 sensor.emit(true); sensor.emit(false); advance(100); sensor.emit(true);
 advance(900); expect({1,0,1,12}); sensor.emit(false); expect({0});
 advance(350); expect({22});
 // More than the advertised maximum is an overflow, not a false double click.
 for (int i=0;i<3;i++) { sensor.emit(true); sensor.emit(false); advance(50); }
 expect({1,0,1,12,0,1,13,0}); advance(350); expect({20});
 // Startup while held never invents a click or long press.
 esphome::matter::MatterComponent owner2;
 esphome::binary_sensor::BinarySensor held;
 held.valid = true; held.state = true;
 MatterSwitchMapping boot(&owner2, &held, 3); boot.register_callbacks();
 advance(1000); expect({}); held.emit(false); expect({});
 // Failed initial scheduling must not fabricate release or complete events.
 fail_schedule = true; sensor.emit(true); expect({});
 fail_schedule = false; sensor.emit(false); advance(1000); expect({});
 sensor.emit(true); sensor.emit(false); advance(350); expect({1,0,21});

}
''')
            subprocess.run(['c++', '-std=c++17', '-I', str(root), str(root / 'main.cpp'),
                            '-o', str(root / 'test')], check=True, capture_output=True)
            subprocess.run([str(root / 'test')], check=True)


if __name__ == '__main__':
    unittest.main()
