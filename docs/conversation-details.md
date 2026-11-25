# Conversation-focused desktop details

The main Lumen detail window prioritizes the conversation. Its narrower right
pane contains reasoning and tool steps only, including failures. Final answer
text stays in the conversation; completing a turn never switches the pane to
another answer view. Closing the pane remains effective across subsequent turns.

Answer actions remain beside the conversation. Explicitly presented files open
through “Show files” in a separate preview with the existing file/image controls.
Closing the detail window cancels the preview workers and closes that preview.
The shared Server Code app owns its own result/step presentation; the old native
Code inspector is not a second active desktop editor.
