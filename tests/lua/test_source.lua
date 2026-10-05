local Source = dofile("resolve/Fusion/Modules/OpenBeat/OpenBeatSource.lua")

local function clip(path, start_frame, end_frame)
  local media = { GetClipProperty = function() return path end }
  return {
    GetMediaPoolItem = function() return media end,
    GetStart = function() return start_frame end,
    GetEnd = function() return end_frame end,
    GetLeftOffset = function() return 12 end,
  }
end

local first = clip("first.wav", 86400, 86412)
local second = clip({ ["File Path"] = "second.wav" }, 86412, 86424)
local timeline = {
  GetCurrentTimecode = function() return "01:00:00:12" end,
  GetTrackCount = function() return 3 end,
  GetItemListInTrack = function(_, _, index)
    if index == 1 then return nil end
    if index == 2 then return { clip("", 86400, 86424), first, second } end
    return { clip("other.wav", 86400, 86424) }
  end,
  GetCurrentVideoItem = function() error("Video item must not select the audio source") end,
}
local path, item = Source.at_playhead(timeline, 23.976)
assert(path == "second.wav" and item == second, "Wrong source at the cut boundary")
local segments = Source.segments_for_path(timeline, "second.wav")
assert(#segments == 1 and segments[1].track_index == 2 and segments[1].left_offset == 12)

timeline.GetCurrentTimecode = function() return "01:00:01:00" end
assert(not pcall(Source.at_playhead, timeline, 24), "Clip end should be exclusive")

timeline.GetCurrentTimecode = function() return "01:00:00;00" end
timeline.GetItemListInTrack = function() return { clip("drop.wav", 107892, 107922) } end
assert(Source.at_playhead(timeline, 29.97) == "drop.wav")
