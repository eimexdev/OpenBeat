local Markers = dofile("resolve/Fusion/Modules/OpenBeat/OpenBeatMarkers.lua")

local function marker(custom, name)
  return { customData = custom, name = name or "old", note = "note", color = "Blue", duration = 2 }
end
local function holder(markers)
  return {
    markers = markers or {},
    GetMarkers = function(self)
      local copy = {}
      for frame, value in pairs(self.markers) do copy[frame] = value end
      return copy
    end,
    DeleteMarkerAtFrame = function(self, frame)
      if self.fail_delete == frame then self.fail_delete = nil; return false end
      self.markers[frame] = nil
      return true
    end,
    AddMarker = function(self, frame, color, name, note, duration, custom)
      if self.fail_add == frame then self.fail_add = nil; return false end
      if self.markers[frame] then return false end
      self.markers[frame] = { color = color, name = name, note = note, duration = duration, customData = custom }
      return true
    end,
  }
end
local custom_a = Markers.custom_data("timeline", "a.wav")
local custom_b = Markers.custom_data("timeline", "b.wav")
local target = holder({ [0] = marker(custom_a), [12] = marker("user"), [24] = marker(custom_b), [36] = marker("OpenBeat:timeline") })
local created, skipped = Markers.replace_many({ {
  holder = target, custom_data = custom_a,
  plan = { { frame = 6, index = 1 }, { frame = 12, index = 2 }, { frame = 24, index = 3 }, { frame = 36, index = 4 } },
} })
assert(created == 1 and skipped == 3)
assert(not target.markers[0] and target.markers[6].customData == custom_a)
assert(target.markers[12].customData == "user" and target.markers[24].customData == custom_b)
assert(target.markers[36].customData == "OpenBeat:timeline", "Legacy ownership is ambiguous")

for _, failure in ipairs({ "add", "delete" }) do
  local first = holder({ [0] = marker(custom_a, "first") })
  local second = holder({ [1] = marker(custom_a, "second") })
  if failure == "add" then second.fail_add = 12 else second.fail_delete = 1 end
  local ok, reason = pcall(Markers.replace_many, {
    { holder = first, custom_data = custom_a, plan = { { frame = 6, index = 1 } } },
    { holder = second, custom_data = custom_a, plan = { { frame = 12, index = 2 } } },
  })
  assert(not ok and reason:find("Previous markers restored", 1, true))
  assert(first.markers[0].name == "first" and first.markers[0].duration == 2 and not first.markers[6])
  assert(second.markers[1].name == "second" and not second.markers[12])
end

local first = holder({ [0] = marker(custom_a) })
local second = { GetMarkers = function() error("Simulated preparation failure") end }
assert(not pcall(Markers.replace_many, {
  { holder = first, custom_data = custom_a, plan = { { frame = 6, index = 1 } } },
  { holder = second, custom_data = custom_a, plan = {} },
}))
assert(first.markers[0] and not first.markers[6], "Preparation must finish before deletion")

local plan = Markers.timeline_plan({ 0, 0.5, 1, 1.5, 2 }, {
  { start_frame = 86400, end_frame = 86424, left_offset = 12 },
  { start_frame = 86400, end_frame = 86424, left_offset = 12 },
}, 24, 86400)
assert(#plan == 2 and plan[1].frame == 0 and plan[1].index == 2 and plan[2].frame == 12)
plan = Markers.clip_plan({ 0.5, 1, 1.5, 2 }, {
  source_start_frame = 30, left_offset = 24, start_frame = 86400, end_frame = 86424,
}, 24, 30)
assert(#plan == 2 and plan[1].frame == 0 and plan[2].frame == 12, "Clip offsets must use timeline frames")
assert(#Markers.source_plan({ 0, 1 }, 24, 1) == 1, "Source end is exclusive")
assert(#Markers.timeline_plan({ 0, 0.01 }, { { start_frame = 0, end_frame = 24, left_offset = 0 } }, 24, 0) == 1)

plan = Markers.timeline_plan({ 0.5, 1, 1.5, 2 }, {
  { source_start_frame = 30, source_fps = 30, left_offset = 30, start_frame = 86400, end_frame = 86424 },
}, 24, 86400)
assert(#plan == 2 and plan[1].frame == 0 and plan[2].frame == 12, "Source and timeline rates must be distinct")
