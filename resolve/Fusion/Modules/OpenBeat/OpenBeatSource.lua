local Source = {}

local module_dir = debug.getinfo(1, "S").source:sub(2):match("^(.*)[/\\][^/\\]+$")
local Timing = dofile(module_dir .. "/OpenBeatTiming.lua")

local function media_path(media)
  if not media then
    return nil
  end
  local path = media:GetClipProperty("File Path")
  if type(path) == "table" then
    path = path["File Path"]
  end
  if type(path) == "string" and path ~= "" then
    return path
  end
  return nil
end

function Source.segments_for_path(timeline, source_path)
  local matches = {}
  for track_index = 1, timeline:GetTrackCount("audio") do
    for _, item in ipairs(timeline:GetItemListInTrack("audio", track_index) or {}) do
      local media = item:GetMediaPoolItem()
      if media_path(media) == source_path then
        table.insert(matches, {
          track_index = track_index,
          timeline_item = item,
          media_pool_item = media,
          start_frame = item:GetStart(),
          end_frame = item:GetEnd(),
          left_offset = item:GetLeftOffset() or 0,
        })
      end
    end
  end
  return matches
end

function Source.at_playhead(timeline, fps)
  local frame = Timing.timecode_to_frame(timeline:GetCurrentTimecode(), fps)
  -- Resolve does not expose the selected timeline audio item. Track order is explicit.
  for track_index = 1, timeline:GetTrackCount("audio") do
    for _, item in ipairs(timeline:GetItemListInTrack("audio", track_index) or {}) do
      if item:GetStart() <= frame and frame < item:GetEnd() then
        local media = item:GetMediaPoolItem()
        local path = media_path(media)
        if path then
          return path, item, media
        end
      end
    end
  end
  error("Place the playhead over a timeline audio clip with a source file before running OpenBeat.")
end

return Source
