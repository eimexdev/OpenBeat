local function write_log(message)
  local path = os.getenv("HOME") .. "/Library/Application Support/Blackmagic Design/DaVinci Resolve/logs/OpenBeatProbe.log"
  local handle = assert(io.open(path, "a"))
  handle:write(os.date("%Y-%m-%d %H:%M:%S "), message, "\n")
  handle:close()
end

local fusion_app = fusion or app
if not fusion_app then
  write_log("UI probe: Fusion app unavailable")
  return
end

local ui = fusion_app.UIManager
if not ui then
  write_log("UI probe: UIManager unavailable")
  return
end

local dispatcher = bmd.UIDispatcher(ui)
local window = dispatcher:AddWindow({
  ID = "OpenBeatUIProbe",
  WindowTitle = "OpenBeat UI Probe",
  Geometry = { 400, 200, 360, 120 },
  ui:VGroup{
    ID = "root",
    ui:Label{
      ID = "message",
      Text = "If you can see this window, UIManager works here.",
      WordWrap = true
    },
    ui:Button{
      ID = "closeButton",
      Text = "Close"
    }
  }
})

function window.On.OpenBeatUIProbe.Close()
  dispatcher:ExitLoop()
end

function window.On.closeButton.Clicked()
  dispatcher:ExitLoop()
end

write_log("UI probe: window created")
window:Show()
dispatcher:RunLoop()
window:Hide()
write_log("UI probe: window closed")
