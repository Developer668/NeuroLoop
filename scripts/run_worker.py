"""Run the local durable worker using the dedicated model environment."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from neuroloop.worker import main, process
if __name__=='__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id')
    args = parser.parse_args()
    if args.run_id:
        process(args.run_id)
    else:
        main()
