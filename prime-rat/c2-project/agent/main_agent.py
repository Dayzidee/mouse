from agent.agent_controller import AgentController

if __name__ == '__main__':
    print("--- Starting C2 Agent ---")
    
    controller = None
    try:
        # Create and start the main controller
        controller = AgentController()
        controller.start()
    except KeyboardInterrupt:
        # Handle Ctrl+C gracefully
        print("\n[Main] Keyboard interrupt received. Shutting down.")
    except Exception as e:
        print(f"[Main] A fatal error occurred: {e}")
    finally:
        if controller:
            controller.stop()
        print("--- C2 Agent Terminated ---")