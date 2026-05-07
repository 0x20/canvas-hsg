-- HSG Canvas: Route incoming Bluetooth A2DP audio to the default speaker sink.
-- Without this, PipeWire may classify BT A2DP source as a capture device
-- instead of routing it to speakers.

bluez_monitor.rules = {
  {
    matches = {
      {
        { "node.name", "matches", "bluez_input.*" },
      },
    },
    apply_properties = {
      ["media.class"] = "Audio/Source",
    },
  },
}
