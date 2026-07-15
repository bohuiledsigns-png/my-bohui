"""Business Graph Engine — 利润路径图谱 MVP

从现有 CRM 数据自动推导节点和边，构建利润路径图谱。
AI 决策从"点判断"升级为"路径判断"。

用法:
    from business_graph.engine import GraphEngine
    g = GraphEngine()
    g.init_graph()                           # 推导节点+边
    paths = g.find_profit_paths("channel", "profit")  # 利润路径发现
    bottlenecks = g.get_bottlenecks()        # 瓶颈检测
"""
import json
import logging
import os
import sqlite3
from collections import defaultdict

logger = logging.getLogger("glowforge.business_graph")

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "crm_data.db")

# 节点类型列表（推导用）
_NODE_TYPES = [
    "customer", "order", "product", "country",
    "channel", "agent", "region", "intent", "pricetier",
]

# 边类型列表
_EDGE_TYPES = [
    "purchase", "profit", "located_in", "belongs_to",
    "acquired_via", "roi", "win_rate", "costs",
    "margin_target", "conversion",
]

# 默认路径评分权重（所有边连乘）
_MAX_PATH_HOPS = 6
_TOP_PATHS = 10


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA query_only = 1")
    return conn


def _get_db_rw():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


class GraphEngine:
    """图引擎 — 利润路径图谱的核心"""

    def __init__(self):
        self._node_count = 0
        self._edge_count = 0

    # ── 主入口 ──

    def init_graph(self):
        """全量推导：清除旧数据 → 生成节点 → 生成边

        返回:
            dict: {nodes, edges, status}
        """
        try:
            self._clear_graph()
            self.derive_nodes()
            self.derive_edges()
            return {
                "nodes": self._node_count,
                "edges": self._edge_count,
                "status": "ok",
            }
        except Exception as e:
            logger.warning("Graph init failed: %s", e)
            return {"nodes": 0, "edges": 0, "status": f"error: {e}"}

    def _clear_graph(self):
        """清空图谱数据（重建时调用）"""
        conn = _get_db_rw()
        try:
            conn.execute("DELETE FROM graph_edges")
            conn.execute("DELETE FROM graph_nodes")
            conn.execute("DELETE FROM profit_paths")
            conn.commit()
            self._node_count = 0
            self._edge_count = 0
        finally:
            conn.close()

    # ── 节点推导 ──

    def derive_nodes(self):
        """从各实体表推导节点"""
        self._node_count = 0
        ops = [
            self._derive_customers,
            self._derive_orders,
            self._derive_products,
            self._derive_countries,
            self._derive_channels,
            self._derive_agents,
            self._derive_regions,
            self._derive_intents,
            self._derive_pricetiers,
        ]
        for op in ops:
            try:
                op()
            except Exception as e:
                logger.warning("Node derivation %s failed: %s", op.__name__, e)
        return self._node_count

    def _insert_node(self, node_id, node_type, label="", metadata=None):
        """插入单个节点"""
        conn = _get_db_rw()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO graph_nodes (id, node_type, label, metadata) VALUES (?, ?, ?, ?)",
                (node_id, node_type, label, json.dumps(metadata or {}, ensure_ascii=False)),
            )
            conn.commit()
            self._node_count += 1
        except Exception:
            pass
        finally:
            conn.close()

    def _derive_customers(self):
        conn = _get_db()
        try:
            rows = conn.execute(
                "SELECT id, name, country, source, lead_status FROM customers"
            ).fetchall()
            for r in rows:
                self._insert_node(
                    f"customer:{r['id']}", "customer",
                    r["name"] or f"Customer#{r['id']}",
                    {"country": r["country"], "source": r["source"], "status": r["lead_status"]},
                )
        finally:
            conn.close()

    def _derive_orders(self):
        conn = _get_db()
        try:
            rows = conn.execute(
                "SELECT id, customer_id, total_amount, status, currency, partner_cost, created_at FROM orders WHERE status != 'cancelled'"
            ).fetchall()
            for r in rows:
                self._insert_node(
                    f"order:{r['id']}", "order",
                    f"Order#{r['id']}",
                    {
                        "amount": r["total_amount"],
                        "currency": r["currency"],
                        "status": r["status"],
                        "customer_id": r["customer_id"],
                        "date": r["created_at"],
                    },
                )
        finally:
            conn.close()

    def _derive_products(self):
        conn = _get_db()
        try:
            # 从 production_costs 表获取产品类别
            rows = conn.execute(
                "SELECT DISTINCT product_category FROM production_costs"
            ).fetchall()
            for r in rows:
                cat = r["product_category"]
                if cat:
                    self._insert_node(f"product:{cat}", "product", cat)
        except Exception:
            pass
        finally:
            conn.close()
        # 同时从 products 表获取
        try:
            conn = _get_db()
            rows = conn.execute(
                "SELECT rowid, specs FROM products"
            ).fetchall()
            for r in rows:
                self._insert_node(
                    f"product:rowid:{r['rowid']}", "product",
                    f"Product#{r['rowid']}",
                    {"specs": r["specs"]},
                )
        except Exception:
            pass
        finally:
            conn.close()

    def _derive_countries(self):
        conn = _get_db()
        try:
            rows = conn.execute(
                "SELECT DISTINCT country FROM customers WHERE country IS NOT NULL AND country != ''"
            ).fetchall()
            for r in rows:
                self._insert_node(f"country:{r['country']}", "country", r["country"])
        finally:
            conn.close()

    def _derive_channels(self):
        conn = _get_db()
        try:
            rows = conn.execute(
                "SELECT DISTINCT source FROM customers WHERE source IS NOT NULL AND source != ''"
            ).fetchall()
            for r in rows:
                self._insert_node(f"channel:{r['source']}", "channel", r["source"])
        finally:
            conn.close()

    def _derive_agents(self):
        # 硬编码 5 个销售 Agent + 从 agent_profiles 表读取
        default_agents = [
            ("hunter_agent", "Hunter (Alex)"),
            ("consultant_agent", "Consultant (Sarah)"),
            ("soft_seller_agent", "Soft Seller (Emma)"),
            ("technical_agent", "Technical (Mike)"),
            ("closer_agent", "Closer (Diana)"),
        ]
        for aid, label in default_agents:
            self._insert_node(f"agent:{aid}", "agent", label)
        # 尝试从 agent_profiles 表补充
        try:
            conn = _get_db()
            rows = conn.execute("SELECT id, name, role FROM agent_profiles").fetchall()
            for r in rows:
                self._insert_node(
                    f"agent:profile:{r['id']}", "agent",
                    r["name"] or r["role"] or f"Agent#{r['id']}",
                )
            conn.close()
        except Exception:
            pass

    def _derive_regions(self):
        # 从 RegionEngine 常量或 regions 表
        default_regions = [
            ("NA", "North America"),
            ("EU", "Europe"),
            ("APAC", "Asia Pacific"),
            ("MEA", "Middle East & Africa"),
            ("LATAM", "Latin America"),
        ]
        for rid, label in default_regions:
            self._insert_node(f"region:{rid}", "region", label)
        try:
            conn = _get_db()
            rows = conn.execute("SELECT id, code, name FROM regions").fetchall()
            for r in rows:
                self._insert_node(
                    f"region:{r['id']}", "region",
                    r["name"] or r["code"] or f"Region#{r['id']}",
                )
            conn.close()
        except Exception:
            pass

    def _derive_intents(self):
        # 从 v3_conversions 获取已有意图
        default_intents = ["询价", "比价", "问工艺", "要样品", "问交期", "下单", "售后", "合作", "要目录", "跟进", "其他"]
        for intent in default_intents:
            self._insert_node(f"intent:{intent}", "intent", intent)
        try:
            conn = _get_db()
            rows = conn.execute(
                "SELECT DISTINCT intent FROM v3_conversions WHERE intent IS NOT NULL AND intent != ''"
            ).fetchall()
            for r in rows:
                self._insert_node(f"intent:{r['intent']}", "intent", r["intent"])
            conn.close()
        except Exception:
            pass

    def _derive_pricetiers(self):
        for tier in ["LOW", "MID", "HIGH", "UNKNOWN"]:
            self._insert_node(f"pricetier:{tier}", "pricetier", tier)

    # ── 边推导 ──

    def derive_edges(self):
        """从各关联表推导边"""
        self._edge_count = 0
        ops = [
            self._derive_customer_order_edges,
            self._derive_order_profit_edges,
            self._derive_customer_country_edges,
            self._derive_customer_channel_edges,
            self._derive_agent_win_rate_edges,
        ]
        for op in ops:
            try:
                op()
            except Exception as e:
                logger.warning("Edge derivation %s failed: %s", op.__name__, e)
        return self._edge_count

    def _insert_edge(self, from_node, to_node, edge_type, weight=1.0, metadata=None):
        """插入单条边"""
        conn = _get_db_rw()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO graph_edges (from_node, to_node, edge_type, weight, metadata) VALUES (?, ?, ?, ?, ?)",
                (from_node, to_node, edge_type, weight, json.dumps(metadata or {}, ensure_ascii=False)),
            )
            conn.commit()
            self._edge_count += 1
        except Exception:
            pass
        finally:
            conn.close()

    def _derive_customer_order_edges(self):
        """customer → order (purchase)  weight=订单金额"""
        conn = _get_db()
        try:
            rows = conn.execute(
                "SELECT id, customer_id, total_amount, created_at FROM orders WHERE status != 'cancelled' AND customer_id IS NOT NULL"
            ).fetchall()
            for r in rows:
                amount = r["total_amount"] or 0
                if amount > 0:
                    self._insert_edge(
                        f"customer:{r['customer_id']}",
                        f"order:{r['id']}",
                        "purchase",
                        weight=min(amount / 1000, 10.0),  # 归一化
                        metadata={"amount": amount, "date": r["created_at"]},
                    )
        finally:
            conn.close()

    def _derive_order_profit_edges(self):
        """order → profit (margin)  weight=利润率"""
        conn = _get_db()
        try:
            rows = conn.execute(
                "SELECT id, total_amount, partner_cost FROM orders WHERE revenue_status = 'closed' AND total_amount > 0"
            ).fetchall()
            for r in rows:
                amount = float(r["total_amount"] or 0)
                cost = float(r["partner_cost"] or 0)
                margin = 1.0 - (cost / amount) if amount > 0 else 0
                self._insert_edge(
                    f"order:{r['id']}",
                    "profit:all",
                    "profit",
                    weight=max(margin, 0),
                    metadata={"margin_pct": round(margin * 100, 1)},
                )
        finally:
            conn.close()

    def _derive_customer_country_edges(self):
        """customer → country (located_in)  weight=1.0"""
        conn = _get_db()
        try:
            rows = conn.execute(
                "SELECT id, country FROM customers WHERE country IS NOT NULL AND country != ''"
            ).fetchall()
            for r in rows:
                self._insert_edge(
                    f"customer:{r['id']}",
                    f"country:{r['country']}",
                    "located_in",
                    weight=1.0,
                )
        finally:
            conn.close()

    def _derive_customer_channel_edges(self):
        """customer → channel (acquired_via)  weight=1.0"""
        conn = _get_db()
        try:
            rows = conn.execute(
                "SELECT id, source FROM customers WHERE source IS NOT NULL AND source != ''"
            ).fetchall()
            for r in rows:
                self._insert_edge(
                    f"customer:{r['id']}",
                    f"channel:{r['source']}",
                    "acquired_via",
                    weight=1.0,
                )
        finally:
            conn.close()

    def _derive_agent_win_rate_edges(self):
        """agent → win_rate (performance)  weight=胜率"""
        # 尝试从 v5_agent_weights 读取
        try:
            conn = _get_db()
            rows = conn.execute(
                "SELECT agent_id, win_rate FROM v5_agent_weights WHERE win_rate > 0"
            ).fetchall()
            for r in rows:
                self._insert_edge(
                    f"agent:{r['agent_id']}",
                    "win_rate:all",
                    "win_rate",
                    weight=r["win_rate"],
                )
            conn.close()
        except Exception:
            pass

    # ── 查询方法 ──

    def get_node(self, node_id):
        """获取单节点"""
        conn = _get_db()
        try:
            r = conn.execute(
                "SELECT * FROM graph_nodes WHERE id = ?", (node_id,)
            ).fetchone()
            return dict(r) if r else None
        finally:
            conn.close()

    def get_nodes(self, node_type=None, limit=100):
        """获取节点列表（按类型筛选）"""
        conn = _get_db()
        try:
            if node_type:
                rows = conn.execute(
                    "SELECT * FROM graph_nodes WHERE node_type = ? ORDER BY node_type LIMIT ?",
                    (node_type, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM graph_nodes ORDER BY node_type LIMIT ?", (limit,)
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_edges(self, from_id=None, edge_type=None, limit=100):
        """获取边列表"""
        conn = _get_db()
        try:
            parts = []
            params = []
            if from_id:
                parts.append("from_node = ?")
                params.append(from_id)
            if edge_type:
                parts.append("edge_type = ?")
                params.append(edge_type)
            where = ("WHERE " + " AND ".join(parts)) if parts else ""
            rows = conn.execute(
                f"SELECT * FROM graph_edges {where} ORDER BY weight DESC LIMIT ?",
                params + [limit],
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── 路径发现 ──

    def find_profit_paths(self, from_type, to_type, top_n=_TOP_PATHS):
        """发现从起点类型到终点类型的高分利润路径

        使用迭代 BFS，最多 _MAX_PATH_HOPS 跳。

        参数:
            from_type: 起点节点类型 (如 "channel")
            to_type: 终点节点类型 (如 "profit")
            top_n: 返回 top N 条路径

        返回:
            list[dict]: [{path, score, hops, nodes}]
        """
        try:
            # 所有边（内存加载，图通常 < 10000 条边）
            conn = _get_db()
            all_edges = [dict(r) for r in conn.execute("SELECT * FROM graph_edges").fetchall()]
            conn.close()

            # 构建邻接表（双向图 — 边方向不影响利润路径）
            adj = defaultdict(list)
            reverse_adj = defaultdict(list)
            for e in all_edges:
                adj[e["from_node"]].append(e)
                reverse_adj[e["to_node"]].append(e)

            # 起点节点
            start_nodes = self.get_nodes(node_type=from_type, limit=200)

            scored_paths = []
            for start in start_nodes:
                # BFS: (path_nodes, score, hops, edges_accumulated)
                queue = [([start["id"]], 1.0, 0, [])]
                while queue:
                    path, score, hops, edge_acc = queue.pop(0)
                    current = path[-1]

                    # 检查当前节点类型是否为目标
                    if current.startswith(f"{to_type}:") or current == to_type:
                        scored_paths.append({
                            "path": list(path),
                            "edges": list(edge_acc),
                            "score": score,
                            "hops": hops,
                        })
                        continue  # 到达目标，不继续扩展

                    if hops >= _MAX_PATH_HOPS:
                        continue  # 超出最大跳数

                    # 扩展（双向遍历）
                    for edge in adj.get(current, []):
                        next_node = edge["to_node"]
                        if next_node not in path:  # 不重复
                            new_score = score * edge["weight"]
                            queue.append((path + [next_node], new_score, hops + 1, edge_acc + [edge]))
                    for edge in reverse_adj.get(current, []):
                        next_node = edge["from_node"]
                        if next_node not in path:
                            new_score = score * edge["weight"]
                            queue.append((path + [next_node], new_score, hops + 1, edge_acc + [edge]))

                # 排序、去重、取 top
            scored_paths.sort(key=lambda x: x["score"], reverse=True)

            # 去重：保留唯一路径
            seen = set()
            unique = []
            for p in scored_paths:
                key = "→".join(p["path"])
                if key not in seen:
                    seen.add(key)
                    unique.append(p)

            # 补充节点和边标签
            node_cache = {}
            for p in unique[:top_n]:
                labels = []
                for nid in p["path"]:
                    if nid not in node_cache:
                        node = self.get_node(nid)
                        node_cache[nid] = node["label"] if node else nid
                    labels.append(node_cache[nid])
                p["labels"] = labels
                # 补充边标签
                for e in p.get("edges", []):
                    e["from_label"] = node_cache.get(e["from_node"], e["from_node"])
                    e["to_label"] = node_cache.get(e["to_node"], e["to_node"])

            return unique[:top_n]
        except Exception as e:
            logger.warning("Profit path discovery failed: %s", e)
            return []

    def score_path(self, path_edges):
        """计算路径分数（边权重连乘）"""
        try:
            score = 1.0
            for edge in path_edges:
                score *= edge.get("weight", 1.0)
            return score
        except Exception:
            return 0.0

    def get_bottlenecks(self, threshold=0.5):
        """检测瓶颈边（低权重边）

        瓶颈 = 权重低于阈值的边，按权重升序排列。

        参数:
            threshold: 权重阈值（默认 0.5）

        返回:
            list[dict]: [{edge_id, from_node, to_node, edge_type, weight}]
        """
        try:
            conn = _get_db()
            rows = conn.execute(
                "SELECT * FROM graph_edges WHERE weight < ? AND weight > 0 ORDER BY weight ASC LIMIT 50",
                (threshold,),
            ).fetchall()
            bottlenecks = [dict(r) for r in rows]
            conn.close()

            # 补充节点标签
            for b in bottlenecks:
                fnode = self.get_node(b["from_node"])
                tnode = self.get_node(b["to_node"])
                b["from_label"] = fnode["label"] if fnode else b["from_node"]
                b["to_label"] = tnode["label"] if tnode else b["to_node"]

            return bottlenecks
        except Exception as e:
            logger.warning("Bottleneck detection failed: %s", e)
            return []

    def get_leverage_points(self):
        """检测杠杆点（利润提升空间最大的边）

        杠杆点 = 低权重边 × 高出现频率（改善它收益最大）

        返回:
            list[dict]: [{edge_type, avg_weight, frequency, leverage_score}]
        """
        try:
            conn = _get_db()
            rows = conn.execute(
                """SELECT edge_type, COUNT(*) as freq, AVG(weight) as avg_weight
                   FROM graph_edges WHERE weight < 1.0
                   GROUP BY edge_type ORDER BY freq * (1.0 - AVG(weight)) DESC LIMIT 10"""
            ).fetchall()
            conn.close()
            result = []
            for r in rows:
                avg_w = r["avg_weight"] or 0
                freq = r["freq"] or 0
                leverage = freq * (1.0 - avg_w)  # 频率 × 改善空间
                result.append({
                    "edge_type": r["edge_type"],
                    "avg_weight": round(avg_w, 3),
                    "frequency": freq,
                    "leverage_score": round(leverage, 3),
                })
            return result
        except Exception as e:
            logger.warning("Leverage point detection failed: %s", e)
            return []

    def get_path_stats(self):
        """图统计摘要"""
        try:
            conn = _get_db()
            node_count = conn.execute("SELECT COUNT(*) as c FROM graph_nodes").fetchone()["c"]
            edge_count = conn.execute("SELECT COUNT(*) as c FROM graph_edges").fetchone()["c"]
            edge_types = conn.execute(
                "SELECT edge_type, COUNT(*) as c FROM graph_edges GROUP BY edge_type ORDER BY c DESC"
            ).fetchall()
            conn.close()
            return {
                "nodes": node_count,
                "edges": edge_count,
                "edge_types": {r["edge_type"]: r["c"] for r in edge_types},
            }
        except Exception as e:
            return {"nodes": 0, "edges": 0, "error": str(e)}
