"""노트북의 회귀 테스트(셀 5~9)를 웹용 core 위에서 그대로 실행한다. API 호출 없음.
inspect.getsource 를 쓰는 테스트가 있어 core+tests 를 임시 파일로 합쳐 __main__ 으로 실행한다."""
import pathlib, runpy, tempfile
root = pathlib.Path(__file__).resolve().parent.parent
core = (root / "study_core.py").read_text(encoding="utf-8")
tests = (root / "tests" / "notebook_cells_5_9.py").read_text(encoding="utf-8")
# cell 7 은 노트북 표시 함수(_display_turn: IPython HTML 한 줄)의 소스 형태를 검사한다. 웹 core 에서도 원본 함수는 그대로 있다.
with tempfile.NamedTemporaryFile("w", suffix="_nbtests.py", delete=False, encoding="utf-8") as f:
    f.write(core + "\n\n" + tests + "\n\nprint('ALL NOTEBOOK REGRESSION TESTS FINISHED')\n")
runpy.run_path(f.name, run_name="__main__")
