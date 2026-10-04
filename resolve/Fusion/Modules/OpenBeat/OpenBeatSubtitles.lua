local Subtitles = {}

function Subtitles.plan(beats, segments, fps, timeline_start)
  local cues = {}
  local function add(start_time, end_time, beat_number)
    start_time = math.max(0, start_time)
    if end_time - start_time >= 0.001 then
      table.insert(cues, { start_time = start_time, end_time = end_time, beat_number = beat_number })
    end
  end
  for _, segment in ipairs(segments) do
    local segment_start = (segment.start_frame - timeline_start) / fps
    local segment_end = (segment.end_frame - timeline_start) / fps
    local source_zero = (segment.start_frame - segment.left_offset - timeline_start) / fps
    if beats[1] then
      add(segment_start, math.min(segment_end, source_zero + beats[1]), nil)
    end
    for index, beat in ipairs(beats) do
      local start_time = math.max(segment_start, source_zero + beat)
      local end_time = math.min(segment_end, beats[index + 1] and source_zero + beats[index + 1] or segment_end)
      add(start_time, end_time, index)
    end
  end
  table.sort(cues, function(a, b)
    if a.start_time ~= b.start_time then return a.start_time < b.start_time end
    if a.end_time ~= b.end_time then return a.end_time < b.end_time end
    return (a.beat_number or 0) < (b.beat_number or 0)
  end)
  local unique = {}
  for _, cue in ipairs(cues) do
    local previous = unique[#unique]
    if not previous or math.abs(cue.start_time - previous.start_time) > 0.0005
      or math.abs(cue.end_time - previous.end_time) > 0.0005
      or cue.beat_number ~= previous.beat_number then
      table.insert(unique, cue)
    end
  end
  return unique
end

local function format_time(seconds)
  local total_ms = math.floor(seconds * 1000 + 0.5)
  local ms = total_ms % 1000
  local total_s = math.floor(total_ms / 1000)
  local s = total_s % 60
  local total_m = math.floor(total_s / 60)
  local m = total_m % 60
  local h = math.floor(total_m / 60)
  return string.format("%02d:%02d:%02d,%03d", h, m, s, ms)
end

function Subtitles.to_srt(cues)
  local lines = {}
  for index, cue in ipairs(cues) do
    table.insert(lines, tostring(index))
    table.insert(lines, format_time(cue.start_time) .. " --> " .. format_time(cue.end_time))
    if cue.beat_number then
      table.insert(lines, "beat " .. cue.beat_number)
      for _, count in ipairs({ 4, 8, 16 }) do
        table.insert(lines, ((cue.beat_number - 1) % count + 1) .. "/" .. count)
      end
    else
      table.insert(lines, "before first beat")
    end
    table.insert(lines, "")
  end
  return table.concat(lines, "\n") .. "\n"
end

return Subtitles
