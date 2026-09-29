# Record the README GIF: brew install vhs && vhs scripts/demo.tape
Output docs/demo.gif
Set FontSize 17
Set Width 1400
Set Height 380
Set Theme "Catppuccin Mocha"
Hide
Type "source .venv/bin/activate && clear"
Enter
Show
Type "rag-eval regress --baseline examples/nimbus/baseline.json --head examples/nimbus/weak.json"
Sleep 500ms
Enter
Sleep 4s
