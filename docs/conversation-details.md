# Conversation-focused desktop details

The main Lumen detail window prioritizes the conversation. Its narrower right
pane contains reasoning and tool steps only, including failures. Final answer
text stays in the conversation; completing a turn never switches the pane to
another answer view. Closing the pane remains effective across subsequent turns.

Answer actions remain beside the conversation. Explicitly presented files open
through “Show files” in a separate preview with the existing file/image controls.
Closing the detail window cancels the preview workers and closes that preview.
The Code Studio inspector continues to use the existing result/step tabs.

Regression coverage: `files/test_studio_focus.py`, the existing Studio and result
suites, German/English disposable native profiles, and the offline Desktop
Simulator. Installed changes are scoped to the surface, detail entry point and
English translations; existing session state is preserved until normal restart.
