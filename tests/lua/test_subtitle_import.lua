local OpenBeat = dofile("resolve/Fusion/Modules/OpenBeat/OpenBeatCommon.lua")
local function upvalue(fn, name)
  for index = 1, 100 do
    local key, value = debug.getupvalue(fn, index)
    if key == name then return value end
    if not key then break end
  end
  error("Missing upvalue " .. name)
end
local place = upvalue(upvalue(OpenBeat.run, "export_subtitles"), "import_subtitles_to_timeline")

for _, failure in ipairs({ "append", "disable" }) do
  local states = { video = { true, false }, subtitle = { false } }
  local fail_once = true
  local timeline = {
    GetTrackCount = function(_, kind) return #states[kind] end,
    AddTrack = function(_, kind) table.insert(states[kind], true); return true end,
    GetIsTrackEnabled = function(_, kind, index) return states[kind][index] end,
    SetTrackEnable = function(_, kind, index, enabled)
      states[kind][index] = enabled
      if failure == "disable" and fail_once then
        fail_once = false
        error("Simulated track failure")
      end
      return true
    end,
    GetItemListInTrack = function() return {} end,
    GetStartFrame = function() return 86400 end,
  }
  local project = { GetMediaPool = function()
    return {
      ImportMedia = function() return { {} } end,
      AppendToTimeline = function() error("Simulated append failure") end,
    }
  end }
  local ok, reason = place({ OpenPage = function() end }, project, timeline, "mock.srt")
  assert(not ok and reason:find("Simulated"))
  assert(states.video[1] == true and states.video[2] == false, "Video states were not restored")
  assert(states.subtitle[1] == false and states.subtitle[2] == true, "Subtitle states were not restored")
end
