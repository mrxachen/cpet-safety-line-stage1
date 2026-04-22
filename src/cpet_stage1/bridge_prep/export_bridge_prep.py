"""
export_bridge_prep.py — Bridge Prep 文档包导出器。

生成阶段 III 桥接准备包，包含：
1. anchor_variable_dictionary_v1.md
2. home_proxy_hypothesis_table_v1.csv
3. bridge_sampling_priority_list_v1.md
4. bridge_question_list_v1.md
5. bridge_prep_package_manifest.json
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from cpet_stage1.bridge_prep.proxy_hypothesis import ProxyHypothesisBuilder

logger = logging.getLogger(__name__)

_DEFAULT_OUTPUT_DIR = "outputs/bridge_prep"


def _load_yaml(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        logger.warning("YAML 文件不存在: %s，返回空字典", path)
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _generate_anchor_variable_dictionary(
    anchor_rules_path: str | Path,
    output_path: str | Path,
) -> Path:
    """从 anchor_rules_v1.yaml 生成锚点变量字典 Markdown。"""
    anchor_cfg = _load_yaml(anchor_rules_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# 锚点变量字典 v1（Anchor Variable Dictionary）",
        "",
        "> 三轴锚点框架：R（储备）/ T（阈值）/ I（不稳定性）",
        "> 来源：`configs/bridge/anchor_rules_v1.yaml`",
        "> 状态：阶段 I 实验室锚点（阶段 II/III 家庭代理待验证）",
        "",
    ]

    for axis_key in ["axis_R", "axis_T", "axis_I"]:
        axis_cfg = anchor_cfg.get(axis_key, {})
        axis_label = axis_key.split("_")[1]
        axis_name = axis_cfg.get("name", axis_key)
        axis_desc = axis_cfg.get("description", "")

        lines.append(f"## 轴 {axis_label}：{axis_name}")
        lines.append(f"_{axis_desc}_")
        lines.append("")
        lines.append("| 变量 ID | 规范字段 | 单位 | 优先级 | 临床含义 | 家庭代理假设 |")
        lines.append("|---|---|---|---|---|---|")

        for var_id, var_info in axis_cfg.get("variables", {}).items():
            canonical = f"`{var_info.get('canonical_field', '')}`"
            unit = var_info.get("unit", "—")
            priority = var_info.get("priority", "")
            clinical = var_info.get("clinical_meaning", "")
            proxy = var_info.get("home_proxy_hypothesis", "")
            lines.append(f"| {var_id} | {canonical} | {unit} | {priority} | {clinical} | {proxy} |")

        lines.append("")

    # 综合评分
    composite = anchor_cfg.get("composite", {})
    if composite:
        lines.append(f"## 综合安全指数：{composite.get('name', 'S_lab')}")
        lines.append("")
        interp = composite.get("interpretation", {})
        for range_str, meaning in interp.items():
            lines.append(f"- **{range_str}**：{meaning}")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("anchor_variable_dictionary_v1.md 已生成: %s", output_path)
    return output_path


def _generate_sampling_priority_list(
    bridge_sampling_path: str | Path,
    output_path: str | Path,
) -> Path:
    """从 bridge_sampling_priority_v0.yaml 生成采样优先级 Markdown。"""
    sampling_cfg = _load_yaml(bridge_sampling_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# 桥接采样优先级列表 v1（Bridge Sampling Priority List）",
        "",
        "> 阶段 II 桥接验证队列招募优先级指南",
        "> 来源：`configs/bridge/bridge_sampling_priority_v0.yaml`",
        "",
    ]

    for tier_key, tier_info in sampling_cfg.get("priority_tiers", {}).items():
        tier_label = tier_key.replace("_", " ").title()
        n_target = tier_info.get("n_target", "?")
        desc = tier_info.get("description", "")
        criteria = tier_info.get("criteria", [])

        lines.append(f"## {tier_label}（目标 n={n_target}）")
        lines.append(f"_{desc}_")
        lines.append("")
        lines.append("**入选标准：**")
        for criterion in criteria:
            if isinstance(criterion, dict):
                for k, v in criterion.items():
                    lines.append(f"- `{k}`: {v}")
            else:
                lines.append(f"- {criterion}")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("bridge_sampling_priority_list_v1.md 已生成: %s", output_path)
    return output_path


def _generate_question_list(
    source_path: str | Path,
    output_path: str | Path,
) -> Path:
    """从 docs/bridge/bridge_question_list_v1.md 复制，若不存在则生成默认内容。"""
    source_path = Path(source_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if source_path.exists():
        content = source_path.read_text(encoding="utf-8")
    else:
        content = (
            "# 桥接问题清单 v1（Bridge Question List）\n\n"
            "阶段 II 需要回答的核心科学问题。\n\n"
            "## Q1：说话测试有效性\n"
            "老年 HTN 患者中，无法说完整句子时的心率（说话测试 HR）是否与 VT1_HR 高度相关（r > 0.70）？\n\n"
            "## Q2：6分钟步行试验作为 VO₂peak 代理\n"
            "6MWT 距离/预测 6MWT（Enright 公式）能否以足够精度预测 VO₂peak%pred（kappa ≥ 0.60）？\n\n"
            "## Q3：家庭 EIH 检测\n"
            "消费级指尖脉搏血氧仪在 6MWT 过程中是否能可靠检测 EIH（灵敏度 ≥ 80%，特异度 ≥ 85%）？\n\n"
            "## Q4：HRV 作为 O₂脉搏替代指标\n"
            "静息 5 分钟 HRV RMSSD 与 O₂脉搏峰值的相关性（r > 0.50）？\n\n"
            "## Q5：RPE 校准\n"
            "黄区患者通常在什么 RPE 水平达到 RCP HR？RPE 14 是否可信？\n"
        )

    output_path.write_text(content, encoding="utf-8")
    logger.info("bridge_question_list_v1.md 已生成: %s", output_path)
    return output_path


def export_bridge_prep_package(
    output_dir: str | Path = _DEFAULT_OUTPUT_DIR,
    anchor_rules_path: str | Path = "configs/bridge/anchor_rules_v1.yaml",
    bridge_sampling_path: str | Path = "configs/bridge/bridge_sampling_priority_v0.yaml",
    home_proxy_map_path: str | Path = "configs/bridge/home_proxy_map_v0.yaml",
    question_list_source: str | Path = "docs/bridge/bridge_question_list_v1.md",
) -> dict[str, Path]:
    """
    生成完整的 Bridge Prep 文档包。

    返回：
        {文件类型: 路径} 字典
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    exported: dict[str, Path] = {}

    # 1. anchor_variable_dictionary_v1.md
    dict_path = _generate_anchor_variable_dictionary(
        anchor_rules_path,
        output_dir / "anchor_variable_dictionary_v1.md",
    )
    exported["anchor_variable_dictionary"] = dict_path

    # 2. home_proxy_hypothesis_table_v1.csv
    proxy_builder = ProxyHypothesisBuilder(anchor_rules_path, home_proxy_map_path)
    proxy_df = proxy_builder.build()
    csv_path = proxy_builder.save(proxy_df, output_dir / "home_proxy_hypothesis_table_v1.csv")
    exported["home_proxy_hypothesis_table"] = csv_path

    # 3. bridge_sampling_priority_list_v1.md
    sampling_path = _generate_sampling_priority_list(
        bridge_sampling_path,
        output_dir / "bridge_sampling_priority_list_v1.md",
    )
    exported["bridge_sampling_priority_list"] = sampling_path

    # 4. bridge_question_list_v1.md
    question_path = _generate_question_list(
        question_list_source,
        output_dir / "bridge_question_list_v1.md",
    )
    exported["bridge_question_list"] = question_path

    # 5. bridge_prep_package_manifest.json
    manifest: dict[str, Any] = {
        "package_name": "bridge_prep_package_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": "v1",
        "stage": "Stage I → Stage II Bridge Preparation",
        "files": {name: str(path) for name, path in exported.items()},
        "file_descriptions": {
            "anchor_variable_dictionary": "三轴锚点变量完整定义（R/T/I 轴）",
            "home_proxy_hypothesis_table": "家庭代理信号假设映射表（待阶段 II 验证）",
            "bridge_sampling_priority_list": "阶段 II 桥接验证队列招募优先级",
            "bridge_question_list": "阶段 II 需回答的核心科学问题",
        },
        "next_steps": [
            "Stage II: 验证家庭代理假设（talk test HR vs VT1_HR，6MWT vs VO2peak%pred）",
            "Stage II: 建立 home safety corridor (C_home)",
            "Stage III: 家庭实时监测验证与 Z_home 校准",
        ],
    }

    manifest_path = output_dir / "bridge_prep_package_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    exported["bridge_prep_manifest"] = manifest_path

    logger.info("Bridge Prep 包已生成: %s (%d 个文件)", output_dir, len(exported))
    return exported
