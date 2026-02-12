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
import { appendFileSync } from "fs"

const DEBUG_LOG = "/var/tmp/debug.log"

function log(message: string): void {
  const timestamp = new Date().toISOString()
  try {
    appendFileSync(DEBUG_LOG, `[${timestamp}] ${message}\n`)
  } catch (e) {
    console.error(`Failed to write debug log: ${e}`)
  }
}

/**
 * Call set_state.sh with state string
 * The script automatically extracts namespace from pwd and session info from tmux
 */
async function setState($: any, state: string): Promise<void> {
  log(`setState called with: ${state}`)
  try {
    await $`$HOME/.waggle/hooks/set_state.sh ${state}`
    log(`setState completed successfully for: ${state}`)
  } catch (error) {
    log(`setState ERROR for ${state}: ${error}`)
    console.error(`[waggle state-tracker] Error calling set_state.sh:`, error)
  }
}

/**
 * OpenCode State Tracker Plugin
 */
export const StateTrackerPlugin: Plugin = async ({ directory, $ }) => {
  log(`Plugin initializing in directory: ${directory}`)
  
  // Read configuration from environment variables with defaults
  const idleState = process.env.OPENCODE_STATE_IDLE || "waiting"
  const workingState = process.env.OPENCODE_STATE_WORKING || "working"
  
  log(`Config: idleState=${idleState}, workingState=${workingState}`)

  // Set initial state to idle when plugin loads (session is waiting for input)
  await setState($, idleState)
  log(`Plugin initialization complete`)
  
  // Register process exit handlers
  process.on('exit', () => {
    log('!!! process.on(exit) fired !!!')
  })
  
  process.on('SIGINT', () => {
    log('!!! process.on(SIGINT) fired !!!')
  })
  
  process.on('SIGTERM', () => {
    log('!!! process.on(SIGTERM) fired !!!')
  })

  return {
    /**
     * Generic event handler - handles session state events
     */
    "event": async (input) => {
      const eventType = input.event?.type || "unknown"
      log(`EVENT received: ${eventType}`)
      
      // Handle session.idle - OpenCode finished responding, back to waiting
      if (input.event?.type === "session.idle") {
        log(`Handling session.idle -> setting idle state`)
        await setState($, idleState)
      }
      
      // Handle session.deleted - OpenCode session ended
      if (input.event?.type === "session.deleted") {
        log(`!!! DETECTED session.deleted -> calling setState --delete !!!`)
        await setState($, "--delete")
      }
      
      // Handle server.instance.disposed - OpenCode process exiting
      if (input.event?.type === "server.instance.disposed") {
        log(`!!! DETECTED server.instance.disposed -> calling setState --delete !!!`)
        await setState($, "--delete")
      }
      
      // Handle AskUserQuestion (question tool) - agent waiting for user input
      if (input.event?.type === "message.part.updated") {
        const part = input.event?.properties?.part
        if (part?.type === "tool" && part?.tool === "question" && part?.state?.status === "running") {
          log(`Detected question tool -> setting idle state`)
          await setState($, idleState)
        }
      }
    },

    /**
     * Handle chat.message event - indicates agent is processing (working state)
     */
    "chat.message": async (input, output) => {
      log(`CHAT.MESSAGE received -> setting working state`)
      await setState($, workingState)
    },

    /**
     * Handle permission.ask event - indicates agent needs user input (idle state)
     */
    "permission.ask": async (input, output) => {
      log(`PERMISSION.ASK received -> setting idle state`)
      await setState($, idleState)
    },
  }
}

// Export as default for easier imports
export default StateTrackerPlugin
