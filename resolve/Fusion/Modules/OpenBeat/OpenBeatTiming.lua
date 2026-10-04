local Timing = {}

function Timing.timecode_to_frame(tc, fps)
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
  if separator == ";" then
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

return Timing
