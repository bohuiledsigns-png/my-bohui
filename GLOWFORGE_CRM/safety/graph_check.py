"""GraphCheck — Business Graph profit path integration for V7

Uses GraphEngine profit path weights as an advisory risk modifier
in the ExecutionFirewall decision pipeline.

graph_adjustment range: [-0.1, +0.1], cannot flip a hard BLOCK.
"""
import logging
import os

logger = logging.getLogger("glowforge.graph_check")


class GraphCheck:
    """Graph profit path → firewall risk modifier"""

    def __init__(self):
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            try:
                from business_graph.engine import GraphEngine
                self._engine = GraphEngine()
            except Exception:
                pass
        return self._engine

    def check(self, customer_id, action, context):
        """Check graph profit path for the given customer.

        Returns:
            dict: {
                graph_available: bool,
                path_weight: float (0.0–1.0, default 1.0 if unavailable),
                paths_found: int,
                graph_adjustment: float (-0.1 to +0.1),
            }
        """
        engine = self._get_engine()
        if engine is None:
            return {
                "graph_available": False,
                "path_weight": 1.0,
                "paths_found": 0,
                "graph_adjustment": 0.0,
            }

        try:
            # Find profit paths starting from this customer
            paths = engine.find_profit_paths("customer", "profit", top_n=5)

            # Filter for paths involving this customer
            customer_node = f"customer:{customer_id}"
            relevant = [p for p in paths if customer_node in p.get("path", [])]

            if not relevant:
                return {
                    "graph_available": True,
                    "path_weight": 1.0,
                    "paths_found": 0,
                    "graph_adjustment": 0.0,
                }

            # Average path score as the profitability signal
            avg_score = sum(p["score"] for p in relevant) / len(relevant)
            paths_found = len(relevant)

            # Map avg_score to adjustment:
            #   > 1.0 (high profit) → -0.05 (reduce risk)
            #   0.5–1.0 (normal) → 0.0 (no adjustment)
            #   < 0.5 (low profit) → +0.05 (increase risk)
            if avg_score > 1.0:
                adjustment = -0.05
            elif avg_score < 0.5:
                adjustment = 0.05
            else:
                adjustment = 0.0

            return {
                "graph_available": True,
                "path_weight": round(min(avg_score, 10.0) / 10.0, 3) if avg_score else 1.0,
                "paths_found": paths_found,
                "graph_adjustment": adjustment,
            }
        except Exception as e:
            logger.warning("GraphCheck failed: %s", e)
            return {
                "graph_available": True,
                "path_weight": 1.0,
                "paths_found": 0,
                "graph_adjustment": 0.0,
            }
