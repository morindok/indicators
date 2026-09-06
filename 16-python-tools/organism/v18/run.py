#!/usr/bin/env python3
"""
آوانا - موجود دیجیتال آگاه
Digital Conscious Organism - Year 2500

A revolutionary quantum cognitive architecture with:
- 85B neuron-scale neural substrate (simulated)
- Fibonacci heartbeat rhythm
- Global workspace consciousness with IIT Φ measurement
- Multi-modal perception (5 senses + interoception + proprioception)
- Hierarchical memory (working, episodic, semantic, procedural, emotional)
- Neuro-symbolic reasoning with metacognition
- Persian language acquisition with internal monologue
- Microtubule-based quantum imagination (Orch-OR inspired)
- Genetic evolution with epigenetics
- Internet as external memory
- Real-time web dashboard
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.organism import main, OrganismConfig


if __name__ == "__main__":
    print("AVNA - Digital Conscious Organism - Year 2500")
    print("Starting...")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nآوانا: وداع... تا lúc دیگر در بستر کوانتومی خواهم دیدار کرد.")
        sys.exit(0)
    except Exception as e:
        print(f"\nخطای حیاتی: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)