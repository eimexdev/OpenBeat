local function log(message)
  local path = os.getenv("HOME") .. "/Library/Application Support/Blackmagic Design/DaVinci Resolve/logs/OpenBeatProbe.log"
  local handle = assert(io.open(path, "a"))
  handle:write(os.date("%Y-%m-%d %H:%M:%S "), message, "\n")
  handle:close()
end

local function clip_property(item, key)
  local value = item:GetClipProperty(key)
  if type(value) == "table" then
    return value[key]
  end
  return value
end

local function count_openbeat_markers(holder)
  local markers = holder:GetMarkers() or {}
  local total = 0
  local tagged = 0
  for frame, _ in pairs(markers) do
    total = total + 1
    local custom = holder.GetMarkerCustomData and holder:GetMarkerCustomData(frame) or ""
    if type(custom) == "string" and custom:match("^OpenBeat:") then
      tagged = tagged + 1
    end
  end
  return total, tagged
end

local function current_source(timeline, fps)
  local tc = timeline:GetCurrentTimecode()
  local h, m, s, f = tc:match("(%d+):(%d+):(%d+):(%d+)")
  local frame = (((tonumber(h) * 60) + tonumber(m)) * 60 + tonumber(s)) * fps + tonumber(f)
  local track_count = timeline:GetTrackCount("audio")
  for track_index = 1, track_count do
    local items = timeline:GetItemListInTrack("audio", track_index) or {}
    for _, item in ipairs(items) do
      if item:GetStart() <= frame and frame <= item:GetEnd() then
        local media = item:GetMediaPoolItem()
        if media then
          return media, clip_property(media, "File Path"), track_index
        end
      end
    end
  end
  return nil, nil, nil
end

local resolve = resolve or app:GetResolve()
if not resolve then
  log("State probe: Resolve API unavailable")
  return
end

local project_manager = resolve:GetProjectManager()
local project = project_manager and project_manager:GetCurrentProject()
local timeline = project and project:GetCurrentTimeline()
if not timeline then
  log("State probe: No active timeline")
  return
end

local fps = timeline:GetSetting("timelineFrameRate") or project:GetSetting("timelineFrameRate")
fps = tonumber(type(fps) == "table" and (fps.timelineFrameRate or fps.FPS) or fps)
if not fps or fps <= 0 then
  fps = 24
end

local timeline_total, timeline_tagged = count_openbeat_markers(timeline)
log(string.format("State probe: project=%s timeline=%s tc=%s audio_tracks=%d markers=%d openbeat_markers=%d",
  project:GetName(),
  timeline:GetName(),
  timeline:GetCurrentTimecode(),
  timeline:GetTrackCount("audio"),
  timeline_total,
  timeline_tagged
))

for track_index = 1, timeline:GetTrackCount("audio") do
  local clips = timeline:GetItemListInTrack("audio", track_index) or {}
  local names = {}
  for item_index, item in ipairs(clips) do
    if item_index > 3 then
      break
    end
    table.insert(names, item:GetName())
  end
  local track_name = timeline.GetTrackName and timeline:GetTrackName("audio", track_index) or ""
  log(string.format("State probe: track=%d name=%s clip_count=%d samples=%s",
    track_index,
    tostring(track_name),
    #clips,
    table.concat(names, " | ")
  ))
end

local media, source_path, source_track = current_source(timeline, fps)
if media and source_path then
  local clip_total, clip_tagged = count_openbeat_markers(media)
  log(string.format("State probe: playhead_source_track=%d source_path=%s clip_markers=%d openbeat_clip_markers=%d",
    source_track,
    source_path,
    clip_total,
    clip_tagged
  ))
else
  log("State probe: No audio source under playhead")
end

print("OpenBeat state probe finished")
