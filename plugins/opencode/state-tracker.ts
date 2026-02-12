/**
 * OpenCode State Tracker Plugin
 * 
 * Tracks OpenCode session state changes and reports them to the waggle state database
 * by calling $HOME/.waggle/hooks/set_state.sh with state strings.
 * 
 * Configuration:
 * - Can be configured via environment variables:
 *   - OPENCODE_STATE_IDLE: State string for idle sessions (default: "waiting")
 *   - OPENCODE_STATE_WORKING: State string for working sessions (default: "working")
 * 
 * Installation:
 * - Copy or symlink this file to .opencode/plugins/
 * - Restart OpenCode to load the plugin
 */

import type { Plugin } from "@opencode-ai/plugin"

/**
 * Call set_state.sh with state string
 * The script automatically extracts namespace from pwd and session info from tmux
 */
async function setState($: any, state: string): Promise<void> {
  try {
    await $`$HOME/.waggle/hooks/set_state.sh ${state}`
  } catch (error) {
    console.error(`[waggle state-tracker] Error calling set_state.sh:`, error)
  }
}

/**
 * OpenCode State Tracker Plugin
 */
export const StateTrackerPlugin: Plugin = async ({ directory, $ }) => {
  // Read configuration from environment variables with defaults
  const idleState = process.env.OPENCODE_STATE_IDLE || "waiting"
  const workingState = process.env.OPENCODE_STATE_WORKING || "working"

  // Set initial state to idle when plugin loads (session is waiting for input)
  await setState($, idleState)

  return {
    /**
     * Generic event handler - handles session state events
     */
    "event": async (input) => {
      // Handle session.idle - OpenCode finished responding, back to waiting
      if (input.event?.type === "session.idle") {
        await setState($, idleState)
      }
      
      // Handle session.deleted - OpenCode session ended
      if (input.event?.type === "session.deleted") {
        await setState($, "--delete")
      }
      
      // Handle server.instance.disposed - OpenCode process exiting
      if (input.event?.type === "server.instance.disposed") {
        await setState($, "--delete")
      }
      
      // Handle AskUserQuestion (question tool) - agent waiting for user input
      if (input.event?.type === "message.part.updated") {
        const part = input.event?.properties?.part
        if (part?.type === "tool" && part?.tool === "question" && part?.state?.status === "running") {
          await setState($, idleState)
        }
      }
    },

    /**
     * Handle chat.message event - indicates agent is processing (working state)
     */
    "chat.message": async (input, output) => {
      await setState($, workingState)
    },

    /**
     * Handle permission.ask event - indicates agent needs user input (idle state)
     */
    "permission.ask": async (input, output) => {
      await setState($, idleState)
    },
  }
}

// Export as default for easier imports
export default StateTrackerPlugin
