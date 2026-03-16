-- Push-to-talk: hold F1 to record, release to stop
-- Adjust nodeBin / cliScript to match your install
local nodeBin   = "/opt/homebrew/bin/node"
local cliScript = os.getenv("HOME") .. "/path-to/phoenix/dist/cli.js"

local voiceTap = hs.eventtap.new(
  {hs.eventtap.event.types.keyDown, hs.eventtap.event.types.keyUp},
  function(event)
    if event:getKeyCode() ~= hs.keycodes.map["f1"] then return false end
    -- Ignore auto-repeat keyDown events (long press generates repeated keyDown)
    if event:getType() == hs.eventtap.event.types.keyDown and event:getProperty(hs.eventtap.event.properties.keyboardEventAutorepeat) ~= 0 then
      return true
    end
    local action = event:getType() == hs.eventtap.event.types.keyDown and "start" or "stop"
    hs.task.new(nodeBin, nil, {cliScript, action}):start()
    return true
  end
)
voiceTap:start()
