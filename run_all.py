"""
Runs the whole pipeline and opens the Power BI template, which reloads the
fresh CSV tables automatically.

    python run_all.py              # pipeline + open Power BI
    python run_all.py --no-pbi     # pipeline only
"""
import os
import sys
import time

import config
import compare_prices
import price_compliance


def main() -> None:
    start = time.time()
    print("Step 1/2 – supplier price comparison")
    compare_prices.main()
    print("\nStep 2/2 – price compliance analysis")
    price_compliance.main()
    print(f"\nDone in {time.time() - start:.0f} s")

    if "--no-pbi" in sys.argv:
        return
    if config.POWERBI_TEMPLATE.exists():
        print(f"Opening {config.POWERBI_TEMPLATE.name} – Power BI will load the new data.")
        os.startfile(config.POWERBI_TEMPLATE)          # Windows
    else:
        print(f"Power BI template not found yet: {config.POWERBI_TEMPLATE}")


if __name__ == "__main__":
    main()
