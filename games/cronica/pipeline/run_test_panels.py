from pipeline.creative_director import CreativeDirector, PlayerAnswer
from pipeline.providers.story_llm_provider import Story, PanelDescription
from pipeline.providers.panel_composition_orchestrator import PanelCompositionOrchestrator
from pathlib import Path

players = [
    PlayerAnswer("p1", "Ana",    [{"prompt_id":"p0","category":"CONCRET","answer_text":"crocodil"},{"prompt_id":"p1","category":"LOC","answer_text":"Sinaia"}]),
    PlayerAnswer("p2", "Bogdan", [{"prompt_id":"p2","category":"CONCRET","answer_text":"umbrelă"},{"prompt_id":"p3","category":"ABSTRACT","answer_text":"teamă"}]),
]
brief = CreativeDirector().generate(players, [], seed=42)

panels = [
    PanelDescription(i, f"Scena {i+1}: Ana și Bogdan la Sinaia.", "", f"Wide shot panel {i+1}, cinematic, comic book style, high contrast", f"Naratorul descrie panoul {i+1}.")
    for i in range(brief.panel_count)
]
story = Story("Test", panels, [p.narrator_line_ro for p in panels], [p.image_prompt_en for p in panels])

out = Path("output/test_run")
result = PanelCompositionOrchestrator().generate_all_panels(brief, story, out)
print(f"Done — {result.success_count} panels in {out.resolve()}")