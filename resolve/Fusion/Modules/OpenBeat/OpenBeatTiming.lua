local Timing = {}

function Timing.frame_rate(setting)
  if type(setting) == "table" then setting = setting.timelineFrameRate or setting.FPS end
  local text = tostring(setting)
  local drop_frame = text:match("%s+[dD][fF]%s*$") ~= nil
  local numeric = text:gsub("%s+[dD][fF]%s*$", "")
  local fps = tonumber(numeric)
  if not fps or fps <= 0 or fps == math.huge then
    error("Could not determine timeline frame rate.")
  end
  return fps, drop_frame
end

function Timing.timecode_to_frame(tc, fps, drop_frame)
  local h, m, s, separator, f = tostring(tc):match("^(%d%d):(%d%d):(%d%d)([:;])(%d+)$")
  if not h then
    error("Unsupported timecode: " .. tostring(tc))
  end
  h, m, s, f = tonumber(h), tonumber(m), tonumber(s), tonumber(f)
  local nominal_fps = math.floor(fps + 0.5)
  if h > 23 or m > 59 or s > 59 or f >= nominal_fps then
    error("Invalid timecode: " .. tc)
  end

  -- Timecode labels count nominal frames, even when playback uses a fractional rate.
  local frame = ((h * 60 + m) * 60 + s) * nominal_fps + f
  if separator == ";" or drop_frame then
    if (nominal_fps ~= 30 and nominal_fps ~= 60)
      or math.abs(fps - nominal_fps * 1000 / 1001) > 0.01 then
      error("Unsupported drop-frame rate: " .. tostring(fps))
    end
    local dropped_per_minute = nominal_fps / 15
    if m % 10 ~= 0 and s == 0 and f < dropped_per_minute then
      error("Invalid drop-frame timecode: " .. tc)
    end
    local minutes = h * 60 + m
    frame = frame - dropped_per_minute * (minutes - math.floor(minutes / 10))
  end
  return frame
end

function Timing.source_start_seconds(segment, fps, clip_fps)
  local source_fps = clip_fps or segment.source_fps
  if segment.source_start_frame ~= nil and source_fps and source_fps > 0 then
    return segment.source_start_frame / source_fps
  end
  return segment.left_offset / fps
end

function Timing.source_zero_seconds(segment, fps, timeline_start)
  return (segment.start_frame - timeline_start) / fps - Timing.source_start_seconds(segment, fps)
end

return Timing
