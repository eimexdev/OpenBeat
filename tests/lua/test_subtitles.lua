local Subtitles = dofile("resolve/Fusion/Modules/OpenBeat/OpenBeatSubtitles.lua")
local segments = {
  { start_frame = 86400, end_frame = 86424, left_offset = 0 },
  { start_frame = 86640, end_frame = 86664, left_offset = 0 },
}
local cues = Subtitles.plan({ 0, 0.5, 1 }, segments, 24, 86400)
assert(#cues == 4, "Cues must stay inside the two source segments")
assert(cues[1].start_time == 0 and cues[2].end_time == 1)
assert(cues[3].start_time == 10 and cues[4].end_time == 11)
assert(cues[1].beat_number == 1 and cues[3].beat_number == 1)
local srt = Subtitles.to_srt(cues)
assert(srt:find("00:00:00,000 --> 00:00:00,500", 1, true))
assert(not srt:find("01:00:", 1, true), "SRT must be relative to the timeline origin")
assert(not srt:find("00:00:01,000 --> 00:00:10,000", 1, true), "Cue crosses a gap")

-- Trims keep the partially visible beat and stop the final cue at the clip end.
cues = Subtitles.plan({ 0.2, 0.7, 1.2, 1.7 }, {
  { start_frame = 240, end_frame = 264, left_offset = 12 },
}, 24, 0)
assert(#cues == 3)
assert(cues[1].start_time == 10 and cues[1].end_time == 10.2 and cues[1].beat_number == 1)
assert(cues[3].end_time == 11)

cues = Subtitles.plan({ 0.2, 0.7 }, {
  { start_frame = 240, end_frame = 264, left_offset = 0 },
  { start_frame = 240, end_frame = 264, left_offset = 0 },
}, 24, 0)
assert(#cues == 3, "Identical overlapping uses should not duplicate cues")
assert(cues[1].start_time == 10 and cues[1].end_time == 10.2 and not cues[1].beat_number)
assert(cues[3].end_time == 11)
assert(#Subtitles.plan({}, segments, 24, 86400) == 0)

cues = Subtitles.plan({ 0.5, 1, 1.5, 2 }, {
  { source_start_frame = 30, source_fps = 30, left_offset = 30, start_frame = 86400, end_frame = 86424 },
}, 24, 86400)
assert(#cues == 2 and cues[1].start_time == 0 and cues[2].start_time == 0.5 and cues[2].end_time == 1)
