"""Owned subprocess entry point; never starts the legacy API or worker."""
import json
from pathlib import Path
import sys


def main():
    request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    output = Path(request["output"])
    output.mkdir(parents=True, exist_ok=True)
    from neuroloop.execution_guard import require_execution_enabled
    require_execution_enabled()
    if request["evaluator"] == "tsam":
        from neuroloop.tsam import predict_video
        result = predict_video(Path(request["path"]), request["details"]["duration"], output)
    elif request["evaluator"] == "tribe":
        from neuroloop.inference import _evaluate_in_process
        result = _evaluate_in_process(Path(request["path"]), request["kind"], request["details"],
            {"include_tsam": False, "include_kragel": True}, output)
    else:
        raise ValueError("Unknown evaluator")
    (output / "report.json").write_text(json.dumps(result, allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    main()
