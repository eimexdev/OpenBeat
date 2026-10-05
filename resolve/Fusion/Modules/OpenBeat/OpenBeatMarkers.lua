local Markers = {}
local module_dir = debug.getinfo(1, "S").source:sub(2):match("^(.*)[/\\][^/\\]+$")
local Timing = dofile(module_dir .. "/OpenBeatTiming.lua")

local function round(value)
  return math.floor(value + 0.5)
end

local function sorted_plan(by_frame)
  local plan = {}
  for frame, index in pairs(by_frame) do
    table.insert(plan, { frame = frame, index = index })
  end
  table.sort(plan, function(a, b) return a.frame < b.frame end)
  return plan
end

function Markers.timeline_plan(beats, segments, fps, timeline_start)
  local by_frame = {}
  for _, segment in ipairs(segments) do
    local source_zero = Timing.source_zero_seconds(segment, fps, timeline_start) * fps
    local start_frame, end_frame = segment.start_frame - timeline_start, segment.end_frame - timeline_start
    for index, beat in ipairs(beats) do
      local position = beat * fps + source_zero
      local frame = round(position)
      if position >= start_frame and position < end_frame and frame >= start_frame and frame < end_frame
        and not by_frame[frame] then
        by_frame[frame] = index
      end
    end
  end
  return sorted_plan(by_frame)
end

function Markers.source_plan(beats, clip_fps, duration)
  local by_frame = {}
  for index, beat in ipairs(beats) do
    local frame = round(beat * clip_fps)
    if beat >= 0 and beat < duration and frame < duration * clip_fps and not by_frame[frame] then
      by_frame[frame] = index
    end
  end
  return sorted_plan(by_frame)
end

function Markers.clip_plan(beats, segment, fps, clip_fps)
  local source_start = Timing.source_start_seconds(segment, fps, clip_fps)
  local duration_frames = segment.end_frame - segment.start_frame
  local by_frame = {}
  for index, beat in ipairs(beats) do
    local position = (beat - source_start) * fps
    local frame = round(position)
    if position >= 0 and position < duration_frames and frame < duration_frames and not by_frame[frame] then
      by_frame[frame] = index
    end
  end
  return sorted_plan(by_frame)
end

function Markers.custom_data(kind, source_path)
  return "OpenBeat:" .. kind .. ":" .. source_path
end

local colors = { "Green", "Blue", "Yellow", "Purple", "Cyan", "Pink", "Red", "Fuchsia" }

local function add(holder, frame, marker)
  return holder:AddMarker(frame, marker.color, marker.name, marker.note, marker.duration, marker.customData)
end

function Markers.replace_many(groups)
  local prepared, skipped = {}, 0
  -- Read and prepare every holder before making any destructive API calls.
  for _, group in ipairs(groups) do
    local existing = group.holder:GetMarkers() or {}
    local owned, planned = {}, {}
    for frame, marker in pairs(existing) do
      local custom = marker.customData
      if custom == nil and group.holder.GetMarkerCustomData then
        custom = group.holder:GetMarkerCustomData(frame)
      end
      if custom == group.custom_data or (group.legacy_custom_data and custom == group.legacy_custom_data) then
        owned[frame] = {
          color = marker.color, name = marker.name, note = marker.note,
          duration = marker.duration, customData = custom,
        }
      end
    end
    for _, entry in ipairs(group.plan) do
      if existing[entry.frame] and not owned[entry.frame] then
        skipped = skipped + 1
      else
        table.insert(planned, {
          frame = entry.frame,
          marker = {
            color = colors[((entry.index - 1) % #colors) + 1], name = "OpenBeat " .. entry.index,
            note = "Created by OpenBeat", duration = 1.0, customData = group.custom_data,
          },
        })
      end
    end
    table.insert(prepared, { holder = group.holder, owned = owned, planned = planned, deleted = {}, added = {} })
  end

  local created = 0
  local ok, reason = pcall(function()
    for _, group in ipairs(prepared) do
      for frame, marker in pairs(group.owned) do
        if not group.holder:DeleteMarkerAtFrame(frame) then
          error("Resolve rejected marker deletion at frame " .. frame)
        end
        group.deleted[frame] = marker
      end
      for _, entry in ipairs(group.planned) do
        if not add(group.holder, entry.frame, entry.marker) then
          error("Resolve rejected marker creation at frame " .. entry.frame)
        end
        table.insert(group.added, entry.frame)
        created = created + 1
      end
    end
  end)
  if not ok then
    local rollback_ok = true
    for index = #prepared, 1, -1 do
      local group = prepared[index]
      for _, frame in ipairs(group.added) do
        local call_ok, deleted = pcall(group.holder.DeleteMarkerAtFrame, group.holder, frame)
        rollback_ok = call_ok and deleted and rollback_ok
      end
      for frame, marker in pairs(group.deleted) do
        local call_ok, restored = pcall(add, group.holder, frame, marker)
        rollback_ok = call_ok and restored and rollback_ok
      end
    end
    local status = rollback_ok and "Previous markers restored." or "Some previous markers could not be restored."
    error("OpenBeat marker update failed. " .. status .. " " .. tostring(reason))
  end
  return created, skipped
end

return Markers
