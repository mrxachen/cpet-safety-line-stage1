"""
CLI entry point for cpet_stage1 pipeline.

Usage:
    cpet-stage1 --help
    cpet-stage1 ingest
    cpet-stage1 qc
    cpet-stage1 cohort
    cpet-stage1 labels
    cpet-stage1 stats table1
    cpet-stage1 stats twobytwo
    cpet-stage1 stats reference
    cpet-stage1 stats plots
    cpet-stage1 stats sensitivity
    cpet-stage1 features
    cpet-stage1 anchors
    cpet-stage1 model p0
    cpet-stage1 model p1
    cpet-stage1 model outcome
    cpet-stage1 stats anomaly
    cpet-stage1 stats concordance
    cpet-stage1 reports
    cpet-stage1 bridge-prep
    cpet-stage1 release
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(
    name="cpet-stage1",
    help="CPET-based exercise safety-line prediction pipeline (Stage I)",
    add_completion=False,
)
console = Console()


@app.command()
def ingest(
    manifest: str = typer.Option(
        "auto",
        help="manifest JSON 路径，'auto' 则使用 data/manifests/batch_cpet_example_manifest.json",
    ),
    config: str = typer.Option("configs/base.yaml", help="基础配置文件路径（暂未使用）"),
    field_map: str = typer.Option(
        "configs/data/field_map_v2.yaml", help="field_map YAML 路径"
    ),
    schema: str = typer.Option("configs/data/schema_v2.yaml", help="schema YAML 路径"),
    output: str = typer.Option(
        "data/staging/cpet_staging_v1.parquet", help="输出 staging parquet 路径"
    ),
) -> None:
    """Excel → staging parquet + field_mapping_report + hash_registry"""
    from cpet_stage1.io.excel_import import ExcelImporter, compute_hash_registry

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]Step 1: Data Ingestion[/bold blue]")

    # 确定 manifest 路径
    manifest_path = (
        Path("data/manifests/batch_cpet_example_manifest.json")
        if manifest == "auto"
        else Path(manifest)
    )
    if not manifest_path.exists():
        console.print(f"[red]manifest 不存在: {manifest_path}[/red]")
        raise typer.Exit(1)

    console.print(f"manifest: {manifest_path}")
    console.print(f"field_map: {field_map}")
    console.print(f"schema: {schema}")

    importer = ExcelImporter(field_map_path=field_map, schema_path=schema)

    # 从 manifest 获取 data_base_dir
    with open(manifest_path, encoding="utf-8") as f:
        manifest_data = json.load(f)

    # 优先使用环境变量
    ext_dir = os.environ.get("EXTERNAL_DATA_DIR")
    if ext_dir:
        data_base_dir = (
            Path(ext_dir) / "clinical_structured/BATCH_CPET_EXAMPLE/S01_GROUPED/raw"
        )
    else:
        data_base_dir = None  # ExcelImporter 会按默认规则查找

    report_path = Path("data/manifests/field_mapping_report.json")
    df = importer.import_batch(
        manifest_path=manifest_path,
        data_base_dir=data_base_dir,
        output_parquet=Path(output),
        report_path=report_path,
    )

    if df.empty:
        console.print("[red]未导入任何数据，请检查数据路径和 manifest 配置[/red]")
        raise typer.Exit(1)

    console.print(f"[green]✓ staging parquet: {output} ({len(df)} 行 × {len(df.columns)} 列)[/green]")
    console.print(f"[green]✓ 映射报告: {report_path}[/green]")

    # hash registry（仅对实际存在的文件）
    if data_base_dir and Path(data_base_dir).exists():
        files = list(Path(data_base_dir).glob("*.xlsx"))
        if files:
            registry = compute_hash_registry(files)
            registry_path = Path("data/manifests/hash_registry.json")
            registry_path.parent.mkdir(parents=True, exist_ok=True)
            with open(registry_path, "w", encoding="utf-8") as f:
                json.dump(registry, f, ensure_ascii=False, indent=2)
            console.print(f"[green]✓ hash registry: {registry_path}[/green]")


@app.command()
def qc(
    staging_path: str = typer.Option(
        "auto",
        help="staging parquet 路径，'auto' 则使用 data/staging/cpet_staging_v1.parquet",
    ),
    rules: str = typer.Option("configs/data/qc_rules_v1.yaml", help="QC 规则 YAML 路径"),
    schema: str = typer.Option("configs/data/schema_v2.yaml", help="schema YAML 路径"),
    curated_out: str = typer.Option(
        "data/curated/cpet_curated_v1.parquet", help="输出 curated parquet 路径"
    ),
    report_out: str = typer.Option("reports/qc_report.md", help="输出 QC 报告路径"),
    flags_out: str = typer.Option(
        "data/curated/qc_flags.parquet", help="输出 QC flags parquet 路径"
    ),
) -> None:
    """staging → curated parquet + qc_report.md + qc_flags"""
    from cpet_stage1.io.loaders import load_staging
    from cpet_stage1.qc.rules import QCEngine
    from cpet_stage1.qc.validators import apply_qc_flags, generate_qc_report

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]Step 2: Quality Control[/bold blue]")

    # 加载 staging 数据
    sp = (
        Path("data/staging/cpet_staging_v1.parquet")
        if staging_path == "auto"
        else Path(staging_path)
    )
    try:
        df = load_staging(sp)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    console.print(f"staging: {sp} ({len(df)} 行)")

    # 运行 QC
    engine = QCEngine(rules_path=rules, schema_path=schema)
    qc_result = engine.run(df)

    # 生成报告
    generate_qc_report(qc_result, df, output_path=report_out)
    console.print(f"[green]✓ QC 报告: {report_out}[/green]")

    # 生成 curated 数据（engine 传入以触发 clip_to_schema_range）
    apply_qc_flags(
        df,
        qc_result,
        curated_path=curated_out,
        flags_path=flags_out,
        engine=engine,
    )
    console.print(f"[green]✓ curated parquet: {curated_out}[/green]")
    console.print(f"[green]✓ QC flags: {flags_out}[/green]")

    # 打印汇总
    s = qc_result.summary
    console.print(
        f"\n[bold]QC 汇总:[/bold] "
        f"总行数={s['n_total']}, "
        f"拒绝={s['n_rejected']}, "
        f"范围越界={s['n_range_violation']}, "
        f"努力度充分={s['n_effort_adequate']} ({s['pct_effort_adequate']:.1f}%)"
    )


@app.command()
def cohort(
    curated_path: str = typer.Option(
        "auto",
        help="curated parquet 路径，'auto' 则使用 data/curated/cpet_curated_v1.parquet",
    ),
    reference_rules: str = typer.Option(
        "configs/data/reference_rules_v2.yaml",
        help="reference_rules YAML 路径",
    ),
    output: str = typer.Option(
        "data/labels/cohort_registry.parquet",
        help="输出 cohort_registry parquet 路径",
    ),
) -> None:
    """curated → cohort_registry.parquet（含 cohort_2x2 + reference_flag）"""
    from cpet_stage1.cohort.cohort_registry import CohortRegistry
    from cpet_stage1.cohort.reference_subset import ReferenceSubsetBuilder
    from cpet_stage1.io.loaders import load_curated

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]Step 3: Cohort Registration[/bold blue]")

    # 加载 curated 数据
    cp = (
        Path("data/curated/cpet_curated_v1.parquet")
        if curated_path == "auto"
        else Path(curated_path)
    )
    try:
        df = load_curated(cp)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    console.print(f"curated: {cp} ({len(df)} 行)")

    # 1. 注册 2×2 队列
    registry = CohortRegistry()
    reg_result = registry.register(df)
    console.print(reg_result.summary())

    # 2. 构建 reference-normal 子集
    ref_path = Path(reference_rules)
    if ref_path.exists():
        builder = ReferenceSubsetBuilder(ref_path)
        ref_result = builder.build(reg_result.df)
        console.print(ref_result.summary())
        out_df = ref_result.df
    else:
        console.print(f"[yellow]reference_rules 不存在: {ref_path}，跳过 reference subset[/yellow]")
        out_df = reg_result.df

    # 3. 保存输出
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(out_path, index=False)
    console.print(f"[green]✓ cohort_registry: {out_path} ({len(out_df)} 行)[/green]")


@app.command()
def labels(
    cohort_path: str = typer.Option(
        "auto",
        help="cohort_registry parquet 路径，'auto' 则使用 data/labels/cohort_registry.parquet",
    ),
    label_rules: str = typer.Option(
        "configs/data/label_rules_v2.yaml",
        help="label_rules YAML 路径",
    ),
    label_out: str = typer.Option(
        "data/labels/label_table.parquet",
        help="输出 label_table parquet 路径",
    ),
    zone_out: str = typer.Option(
        "data/labels/zone_table.parquet",
        help="输出 zone_table parquet 路径",
    ),
) -> None:
    """cohort_registry → label_table + zone_table + leakage_guard 验证"""
    from cpet_stage1.labels.label_engine import LabelEngine
    from cpet_stage1.labels.leakage_guard import LeakageGuard
    from cpet_stage1.labels.safety_zone import generate_zone_report

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]Step 4: Label Generation[/bold blue]")

    # 加载 cohort_registry
    cp = (
        Path("data/labels/cohort_registry.parquet")
        if cohort_path == "auto"
        else Path(cohort_path)
    )
    if not cp.exists():
        console.print(f"[red]cohort_registry 不存在: {cp}\n请先运行 'make cohort'[/red]")
        raise typer.Exit(1)

    import pandas as pd

    df = pd.read_parquet(cp)
    console.print(f"cohort_registry: {cp} ({len(df)} 行)")

    # 生成标签
    engine = LabelEngine(label_rules)
    result = engine.run(df)

    console.print(result.report())

    # P0 合理性检查
    p0_pct = result.summary["p0_positive_pct"]
    if p0_pct < 5:
        console.print(f"[yellow]⚠ P0 阳性率偏低 ({p0_pct:.1f}%)，请检查标签规则[/yellow]")
    elif p0_pct > 50:
        console.print(f"[yellow]⚠ P0 阳性率偏高 ({p0_pct:.1f}%)，请检查标签规则[/yellow]")

    # P1 红区检查
    n_total = result.summary["n_total"]
    red_pct = 100 * result.summary["p1_red"] / n_total if n_total > 0 else 0
    if red_pct >= 40:
        console.print(f"[yellow]⚠ P1 红区占比偏高 ({red_pct:.1f}%)，请检查标签规则[/yellow]")

    # leakage_guard 验证（只检测 feature_config P0 列，而非全 df 列）
    # 注意：df 是原始测量数据，包含 bp_peak_sys 等不在 P0 特征集中的列；
    # 使用全 df 会误报。正确做法：加载 feature_config 提取 P0 特征列后再检查。
    guard = LeakageGuard.from_config(label_rules)
    try:
        import yaml
        _feat_cfg_path = Path("configs/features/feature_config_v1.yaml")
        with open(_feat_cfg_path) as _f:
            _feat_cfg = yaml.safe_load(_f)
        _p0_cfg = _feat_cfg.get("p0", {})
        _p0_cols = (
            _p0_cfg.get("continuous", [])
            + _p0_cfg.get("binary", [])
            + _p0_cfg.get("categorical", [])
            + _p0_cfg.get("protocol", [])
        )
        # 只取 df 中实际存在的 P0 特征列
        X_p0 = df[[c for c in _p0_cols if c in df.columns]]
        guard.assert_no_leakage(X_p0, task="p0")
        console.print("[green]✓ leakage_guard P0: 通过[/green]")
    except AssertionError as e:
        console.print(f"[red]✗ leakage_guard P0: {e}[/red]")
    except Exception as e:
        console.print(f"[yellow]⚠ leakage_guard P0 跳过（无法加载 feature_config）: {e}[/yellow]")

    # 保存输出
    engine.save(result, label_path=label_out, zone_path=zone_out)
    console.print(f"[green]✓ label_table: {label_out}[/green]")
    console.print(f"[green]✓ zone_table: {zone_out}[/green]")

    # 保存区域报告
    report_str = generate_zone_report(result, df)
    report_path = Path("reports/zone_report.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_str, encoding="utf-8")
    console.print(f"[green]✓ zone_report: {report_path}[/green]")


stats_app = typer.Typer(help="M4 统计分析命令组：Table 1 / 双因素 / 参考方程 / 绘图 / 敏感性")
app.add_typer(stats_app, name="stats")

_DEFAULT_COHORT_PARQUET = "data/labels/cohort_registry.parquet"
_DEFAULT_STATS_CONFIG = "configs/stats/table1_config.yaml"


def _load_cohort_df(cohort_path: str) -> "pd.DataFrame":
    """加载 cohort_registry parquet（含 labels 列）。"""
    import pandas as pd

    cp = Path(cohort_path)
    if not cp.exists():
        console.print(f"[red]cohort 文件不存在: {cp}\n请先运行 'make labels'[/red]")
        raise typer.Exit(1)
    return pd.read_parquet(cp)


@stats_app.command("table1")
def stats_table1(
    cohort_path: str = typer.Option(_DEFAULT_COHORT_PARQUET, help="cohort_registry parquet 路径"),
    config: str = typer.Option(_DEFAULT_STATS_CONFIG, help="stats 配置 YAML 路径"),
    output_md: str = typer.Option("reports/table1.md", help="输出 Markdown 路径"),
    output_csv: str = typer.Option("reports/table1.csv", help="输出 CSV 路径"),
) -> None:
    """生成 Table 1 基线特征表。"""
    from cpet_stage1.stats.table1 import Table1Builder

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]M4: Table 1 基线特征表[/bold blue]")

    df = _load_cohort_df(cohort_path)
    console.print(f"数据: {cohort_path} ({len(df)} 行)")

    builder = Table1Builder(config)
    result = builder.build(df)

    result.to_markdown(output_md)
    result.to_csv(output_csv)

    console.print(f"[green]✓ Table 1 Markdown: {output_md}[/green]")
    console.print(f"[green]✓ Table 1 CSV: {output_csv}[/green]")
    console.print(f"[green]✓ 变量数: {len(result.table)} 行[/green]")


@stats_app.command("twobytwo")
def stats_twobytwo(
    cohort_path: str = typer.Option(_DEFAULT_COHORT_PARQUET, help="cohort_registry parquet 路径"),
    config: str = typer.Option(_DEFAULT_STATS_CONFIG, help="stats 配置 YAML 路径"),
    output_md: str = typer.Option("reports/twobytwo.md", help="输出 Markdown 路径"),
) -> None:
    """HTN × EIH 双因素效应分析（Two-way ANOVA + 偏η²）。"""
    from cpet_stage1.stats.twobytwo import TwoByTwoAnalyzer

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]M4: HTN × EIH 双因素效应分析[/bold blue]")

    df = _load_cohort_df(cohort_path)
    console.print(f"数据: {cohort_path} ({len(df)} 行)")

    analyzer = TwoByTwoAnalyzer(config)
    result = analyzer.run(df)

    result.to_markdown(output_md)
    console.print(f"[green]✓ 双因素分析报告: {output_md}[/green]")
    console.print(f"[green]✓ 结局变量数: {len(result.anova_table)}[/green]")


@stats_app.command("reference")
def stats_reference(
    cohort_path: str = typer.Option(_DEFAULT_COHORT_PARQUET, help="cohort_registry parquet 路径"),
    config: str = typer.Option(_DEFAULT_STATS_CONFIG, help="stats 配置 YAML 路径"),
    output_md: str = typer.Option("reports/reference_equations.md", help="输出 Markdown 路径"),
    output_parquet: str = typer.Option(
        "data/labels/reference_scores.parquet", help="含 %pred/z-score 的输出 parquet"
    ),
) -> None:
    """构建参考正常方程，计算 %pred 和 z-score。"""
    from cpet_stage1.stats.reference_builder import ReferenceBuilder

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]M4: 参考正常方程[/bold blue]")

    df = _load_cohort_df(cohort_path)
    console.print(f"数据: {cohort_path} ({len(df)} 行)")

    builder = ReferenceBuilder(config)
    result = builder.build(df)

    result.to_markdown(output_md)
    console.print(f"[green]✓ 参考方程报告: {output_md}[/green]")

    # 保存 %pred / z-score 列
    if not result.pred_df.empty:
        out_path = Path(output_parquet)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        result.pred_df.to_parquet(out_path, index=False)
        console.print(f"[green]✓ %pred/z-score parquet: {output_parquet}[/green]")

    console.print(f"[green]✓ 方程数: {len(result.equations)}[/green]")


@stats_app.command("plots")
def stats_plots(
    cohort_path: str = typer.Option(_DEFAULT_COHORT_PARQUET, help="cohort_registry parquet 路径"),
    config: str = typer.Option(_DEFAULT_STATS_CONFIG, help="stats 配置 YAML 路径"),
    output_dir: str = typer.Option("reports/figures/m4", help="图表输出目录"),
) -> None:
    """生成 M4 所有图表（箱线图/小提琴图/交互作用图）。"""
    from cpet_stage1.stats.plots import generate_all_m4_plots

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]M4: 统计图表生成[/bold blue]")

    df = _load_cohort_df(cohort_path)
    console.print(f"数据: {cohort_path} ({len(df)} 行)")

    generated = generate_all_m4_plots(df, config, output_dir)
    console.print(f"[green]✓ 生成图表: {len(generated)} 张[/green]")
    for p in generated:
        console.print(f"  [dim]{p}[/dim]")


@stats_app.command("sensitivity")
def stats_sensitivity(
    cohort_path: str = typer.Option(_DEFAULT_COHORT_PARQUET, help="cohort_registry parquet 路径"),
    config: str = typer.Option(_DEFAULT_STATS_CONFIG, help="stats 配置 YAML 路径"),
    output_md: str = typer.Option("reports/sensitivity_protocol.md", help="输出 Markdown 路径"),
) -> None:
    """协议分层敏感性分析（按运动协议分组重跑 Table 1）。"""
    import pandas as pd
    import yaml

    from cpet_stage1.stats.table1 import Table1Builder, build_stratified_table1

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]M4: 协议敏感性分析[/bold blue]")

    df = _load_cohort_df(cohort_path)

    # 读取敏感性配置
    cfg_path = Path(config)
    with open(cfg_path, encoding="utf-8") as f:
        full_cfg = yaml.safe_load(f) or {}
    sens_cfg = full_cfg.get("sensitivity", {})

    # 推导 protocol_type 列
    from_col = sens_cfg.get("protocol_derivation", {}).get("from_column", "exercise_protocol_cycle")
    mapping = sens_cfg.get("protocol_derivation", {}).get("mapping", {True: "cycle", False: "treadmill"})
    fallback = sens_cfg.get("protocol_derivation", {}).get("fallback", "unknown")
    stratify_col = sens_cfg.get("stratify_column", "protocol_type")

    if from_col in df.columns:
        df[stratify_col] = df[from_col].map(
            lambda v: mapping.get(bool(v) if pd.notna(v) else None, fallback)
        )
    else:
        df[stratify_col] = fallback
        console.print(f"[yellow]⚠ 协议列 '{from_col}' 不存在，全部设为 '{fallback}'[/yellow]")

    console.print(f"协议分布:\n{df[stratify_col].value_counts().to_string()}")

    builder = Table1Builder(config)
    results = build_stratified_table1(builder, df, stratify_col)

    # 生成分层报告
    lines = ["# 协议分层敏感性分析", ""]
    for stratum, res in results.items():
        n = sum(res.group_n.values())
        lines.append(f"## 协议：{stratum}（n={n}）")
        lines.append("")
        lines.append(res.to_markdown())
        lines.append("")

    md_str = "\n".join(lines)
    out_path = Path(output_md)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md_str, encoding="utf-8")

    console.print(f"[green]✓ 敏感性分析报告: {output_md}[/green]")
    console.print(f"[green]✓ 分层数: {len(results)}[/green]")


@stats_app.command("posthoc")
def stats_posthoc(
    cohort_path: str = typer.Option(_DEFAULT_COHORT_PARQUET, help="cohort_registry parquet 路径"),
    output_md: str = typer.Option("reports/posthoc_report.md", help="输出 Markdown 路径"),
    group_col: str = typer.Option("group_code", help="分组列名"),
) -> None:
    """Dunn's post-hoc 两两比较检验（KW 后处理）。"""
    import pandas as pd
    from cpet_stage1.stats.posthoc import DunnPosthoc, generate_posthoc_report

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]M4+: Dunn's Post-hoc 检验[/bold blue]")

    df = _load_cohort_df(cohort_path)
    # 合并标签表（包含 eih_status 等列）
    label_p = Path("data/labels/label_table.parquet")
    if label_p.exists():
        lt = pd.read_parquet(label_p)
        for col in lt.columns:
            if col not in df.columns:
                df[col] = lt[col].values

    # 选择连续变量（与 Table 1 一致的关键指标）
    key_vars = [
        "age", "height_cm", "weight_kg",
        "vo2_peak", "hr_peak", "o2_pulse_peak",
        "vt1_vo2", "ve_vco2_slope", "vo2_peak_pct_pred",
        "hr_recovery", "oues", "mets_peak",
    ]
    variables = [v for v in key_vars if v in df.columns]
    console.print(f"分析变量: {variables}")

    analyzer = DunnPosthoc()
    results = analyzer.run(df, variables=variables, group_col=group_col)

    generate_posthoc_report(results, output_path=output_md)
    sig_vars = [v for v, r in results.items() if r.significant_pairs]
    console.print(f"[green]✓ Post-hoc 报告: {output_md}[/green]")
    console.print(f"[green]✓ 显著差异变量: {len(sig_vars)}/{len(results)}[/green]")


@stats_app.command("zone-v2")
def stats_zone_v2(
    cohort_path: str = typer.Option(_DEFAULT_COHORT_PARQUET, help="cohort_registry parquet 路径"),
    label_path: str = typer.Option("data/labels/label_table.parquet", help="label_table parquet 路径"),
    output_report: str = typer.Option("reports/zone_engine_v2_report.md", help="报告输出路径"),
    output_parquet: str = typer.Option("data/labels/zone_table_v2.parquet", help="zone_table_v2 输出路径"),
    n_bootstrap: int = typer.Option(500, help="Bootstrap 次数"),
) -> None:
    """Phase F Step 2：数据驱动安全区引擎 v2（R/T/I 重构 + 参考人群切点 + 个性化）。"""
    import pandas as pd
    from cpet_stage1.labels.zone_engine_v2 import ZoneEngineV2

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]Phase F Step 2: 数据驱动安全区 v2[/bold blue]")

    df = _load_cohort_df(cohort_path)

    # 合并 label_table
    lp = Path(label_path)
    if lp.exists():
        labels = pd.read_parquet(lp)
        for col in labels.columns:
            if col not in df.columns:
                df[col] = labels[col].values

    # EIH status from cohort_2x2
    if "eih_status" not in df.columns and "cohort_2x2" in df.columns:
        df["eih_status"] = df["cohort_2x2"].str.contains("EIH", na=False)

    engine = ZoneEngineV2(n_bootstrap=n_bootstrap)
    result = engine.build(df, output_path=output_report)

    # 保存 zone_table_v2
    zone_cols = ["z_lab_v2", "s_lab_v2", "r_score_v2", "t_score_v2", "i_score_v2"]
    zone_df = result.df[["subject_id"] + [c for c in zone_cols if c in result.df.columns]].copy()
    Path(output_parquet).parent.mkdir(parents=True, exist_ok=True)
    zone_df.to_parquet(output_parquet, index=False)

    w = result.axis_weights
    console.print(f"  轴权重: R={w.r_weight:.3f}, T={w.t_weight:.3f}, I={w.i_weight:.3f}")
    cp = result.global_cutpoints
    console.print(f"  切点: low={cp.low:.2f}, high={cp.high:.2f} (Youden's J={cp.youden_j:.3f})")
    dist = result.zone_distribution.get("global", {})
    console.print(f"  Zone分布: Green={dist.get('green',0)}, Yellow={dist.get('yellow',0)}, Red={dist.get('red',0)}")
    console.print(f"[bold green]✓ Zone v2 报告: {output_report}[/bold green]")
    console.print(f"[bold green]✓ Zone v2 表格: {output_parquet}[/bold green]")


@stats_app.command("reference-v2")
def stats_reference_v2(
    cohort_path: str = typer.Option(_DEFAULT_COHORT_PARQUET, help="cohort_registry parquet 路径"),
    output_path: str = typer.Option("reports/reference_equation_v2.md", help="输出 Markdown 报告路径"),
) -> None:
    """Phase F Step 1：改进参考方程（含 BMI + CV 模型选择 + 外部方程对比）。"""
    from cpet_stage1.stats.reference_builder_v2 import build_reference_v2

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]Phase F Step 1: 改进参考方程 v2[/bold blue]")

    df = _load_cohort_df(cohort_path)

    v1_r2_map = {
        "vo2_peak": 0.298,
        "hr_peak": 0.050,
        "ve_vco2_slope": 0.030,
        "o2_pulse_peak": 0.200,
    }

    result = build_reference_v2(df, v1_r2_map=v1_r2_map, output_path=output_path)

    for _, row in result.diagnostics.iterrows():
        console.print(f"  {row['目标变量']}: v1={row['v1 R²']} → v2={row['v2 R²（拟合）']} ({row['ΔR²']})")

    console.print(f"[bold green]✓ 参考方程 v2 报告已生成：{output_path}[/bold green]")


@stats_app.command("zone-sensitivity")
def stats_zone_sensitivity(
    cohort_path: str = typer.Option(_DEFAULT_COHORT_PARQUET, help="cohort_registry parquet 路径"),
    label_path: str = typer.Option("data/labels/label_table.parquet", help="label_table parquet 路径"),
    output_path: str = typer.Option("reports/zone_sensitivity_report.md", help="报告输出路径"),
    n_bootstrap: int = typer.Option(1000, help="Bootstrap 次数"),
) -> None:
    """Phase F Step 3：Zone 边界验证与敏感性分析（Bootstrap CI + 文献对比 + 亚组一致性）。"""
    import pandas as pd
    from cpet_stage1.labels.zone_engine_v2 import ZoneEngineV2
    from cpet_stage1.stats.zone_sensitivity import run_sensitivity_analysis

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]Phase F Step 3: Zone 敏感性分析[/bold blue]")

    df = _load_cohort_df(cohort_path)

    lp = Path(label_path)
    if lp.exists():
        import pandas as _pd
        labels = _pd.read_parquet(lp)
        for col in labels.columns:
            if col not in df.columns:
                df[col] = labels[col].values

    if "eih_status" not in df.columns and "cohort_2x2" in df.columns:
        df["eih_status"] = df["cohort_2x2"].str.contains("EIH", na=False)

    engine = ZoneEngineV2(n_bootstrap=200)
    zone_result = engine.build(df)

    sens_result = run_sensitivity_analysis(
        zone_result.df,
        output_path=output_path,
        n_bootstrap=n_bootstrap,
    )

    for ci_name, (lo, hi) in sens_result.bootstrap_ci.items():
        console.print(f"  {ci_name}: [{lo:.2f}, {hi:.2f}]")

    console.print(f"[bold green]✓ 敏感性分析报告: {output_path}[/bold green]")


@stats_app.command("data-audit")
def stats_data_audit(
    staging_path: str = typer.Option("data/staging/cpet_staging_v1.parquet", help="staging parquet 路径"),
    output_path: str = typer.Option("reports/data_audit_full.md", help="输出 Markdown 路径"),
) -> None:
    """Phase F Step 0：深度数据审计（全字段完整度+分布统计）。"""
    from cpet_stage1.stats.data_audit import run_data_audit

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]Phase F Step 0: 深度数据审计[/bold blue]")

    run_data_audit(staging_path=staging_path, output_path=output_path)

    console.print(f"[bold green]✓ 数据审计报告已生成：{output_path}[/bold green]")


@stats_app.command("supplement-plots")
def stats_supplement_plots(
    cohort_path: str = typer.Option(_DEFAULT_COHORT_PARQUET, help="cohort_registry parquet 路径"),
    output_dir: str = typer.Option("reports/figures/supplement", help="补充图表输出目录"),
) -> None:
    """生成 Phase A3 补充图表（zone分布、缺失热力图、相关热力图、安全区概念图）。"""
    import pandas as pd
    from cpet_stage1.stats.plots import generate_all_supplementary_plots
    from cpet_stage1.stats.logistic_eih import EIHLogisticAnalyzer

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]Phase A3: 补充图表生成[/bold blue]")

    df = _load_cohort_df(cohort_path)
    # 合并 zone 表
    for parquet_path in [
        "data/labels/label_table.parquet",
        "data/anchors/anchor_table.parquet",
    ]:
        p = Path(parquet_path)
        if p.exists():
            extra = pd.read_parquet(p)
            for col in extra.columns:
                if col not in df.columns:
                    df[col] = extra[col].values

    # 派生 BMI
    if "bmi" not in df.columns and "height_cm" in df.columns and "weight_kg" in df.columns:
        height_m = df["height_cm"] / 100.0
        df["bmi"] = df["weight_kg"] / (height_m ** 2)

    # 生成 EIH 森林图数据
    eih_forest_df = None
    if "eih_status" in df.columns:
        try:
            analyzer = EIHLogisticAnalyzer()
            eih_result = analyzer.run(df, outcome="eih_status", use_p0_only=True)
            eih_forest_df = eih_result.to_forest_data()
        except Exception as e:
            console.print(f"[yellow]EIH Logistic 跳过: {e}[/yellow]")

    generated = generate_all_supplementary_plots(
        df, output_dir=output_dir, eih_forest_df=eih_forest_df
    )

    console.print(f"[bold green]✓ 补充图表: {len(generated)} 张 → {output_dir}[/bold green]")
    for fp in generated:
        console.print(f"  {fp}")


@stats_app.command("eih-logistic")
def stats_eih_logistic(
    cohort_path: str = typer.Option(_DEFAULT_COHORT_PARQUET, help="cohort_registry parquet 路径"),
    output_md: str = typer.Option("reports/eih_logistic_report.md", help="输出 Markdown 路径"),
    p0_only: bool = typer.Option(False, help="仅使用运动前字段（严格 P0 约束）"),
) -> None:
    """EIH 多因素 Logistic 回归分析（独立预测因子）。"""
    import pandas as pd
    from cpet_stage1.stats.logistic_eih import EIHLogisticAnalyzer, generate_eih_logistic_report

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]M4+: EIH Logistic 回归分析[/bold blue]")

    df = _load_cohort_df(cohort_path)
    # 合并标签表
    label_p = Path("data/labels/label_table.parquet")
    if label_p.exists():
        lt = pd.read_parquet(label_p)
        for col in lt.columns:
            if col not in df.columns:
                df[col] = lt[col].values

    # 派生 BMI（如未存在）
    if "bmi" not in df.columns and "height_cm" in df.columns and "weight_kg" in df.columns:
        height_m = df["height_cm"] / 100.0
        df["bmi"] = df["weight_kg"] / (height_m ** 2)

    analyzer = EIHLogisticAnalyzer()
    result = analyzer.run(df, outcome="eih_status", use_p0_only=p0_only)
    generate_eih_logistic_report(result, output_path=output_md)

    console.print(f"[green]✓ EIH Logistic 报告: {output_md}[/green]")
    console.print(f"[green]  样本: N={result.n_total}, EIH+={result.n_eih_positive} ({result.eih_rate:.1%})[/green]")
    console.print(f"[green]  多因素收敛: {'✓' if result.converged else '✗'}[/green]")


@stats_app.command("subgroup")
def stats_subgroup(
    cohort_path: str = typer.Option(_DEFAULT_COHORT_PARQUET, help="cohort_registry parquet 路径"),
    zone_col: str = typer.Option("p1_zone", help="P1 zone 列名"),
    output_md: str = typer.Option("reports/subgroup_report.md", help="输出 Markdown 路径"),
) -> None:
    """亚组分析（性别 / 年龄中位数 / EIH+EIH- / HTN+HTN-）。"""
    import pandas as pd
    from cpet_stage1.stats.subgroup import SubgroupAnalyzer, generate_subgroup_report

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]M4+: 亚组分析[/bold blue]")

    df = _load_cohort_df(cohort_path)
    # 合并标签表（获取 zone 信息）
    for label_file in [
        "data/labels/label_table.parquet",
        "data/labels/zone_table.parquet",
    ]:
        lp = Path(label_file)
        if lp.exists():
            lt = pd.read_parquet(lp)
            for col in lt.columns:
                if col not in df.columns:
                    try:
                        df[col] = lt[col].values
                    except Exception:
                        pass

    analyzer = SubgroupAnalyzer()
    results = []

    # 性别亚组
    if "sex" in df.columns:
        try:
            r = analyzer.run_sex(df, zone_col=zone_col)
            results.append(r)
            console.print(f"[green]✓ 性别亚组: {len(r.summaries)} 组[/green]")
        except Exception as e:
            console.print(f"[yellow]性别亚组失败: {e}[/yellow]")

    # 年龄中位数亚组
    if "age" in df.columns:
        try:
            r = analyzer.run_age_median(df, zone_col=zone_col)
            results.append(r)
            console.print(f"[green]✓ 年龄中位数亚组: {len(r.summaries)} 组[/green]")
        except Exception as e:
            console.print(f"[yellow]年龄亚组失败: {e}[/yellow]")

    # EIH 亚组
    if "eih_status" in df.columns:
        try:
            r = analyzer.run_eih(df, zone_col=zone_col)
            results.append(r)
            console.print(f"[green]✓ EIH 亚组: {len(r.summaries)} 组[/green]")
        except Exception as e:
            console.print(f"[yellow]EIH 亚组失败: {e}[/yellow]")

    # HTN 亚组
    if "htn_history" in df.columns:
        try:
            r = analyzer.run_htn(df, zone_col=zone_col)
            results.append(r)
            console.print(f"[green]✓ HTN 亚组: {len(r.summaries)} 组[/green]")
        except Exception as e:
            console.print(f"[yellow]HTN 亚组失败: {e}[/yellow]")

    if results:
        generate_subgroup_report(results, output_path=output_md)
        console.print(f"[green]✓ 亚组分析报告: {output_md}[/green]")
        console.print(f"[green]  共 {len(results)} 个分层维度[/green]")
    else:
        console.print("[red]无可用亚组分析[/red]")


@app.command()
def features(
    cohort_path: str = typer.Option(
        "auto",
        help="cohort_registry parquet 路径，'auto' 则使用 data/labels/cohort_registry.parquet",
    ),
    feature_config: str = typer.Option(
        "configs/features/feature_config_v1.yaml",
        help="feature_config YAML 路径",
    ),
    label_rules: str = typer.Option(
        "configs/data/label_rules_v2.yaml",
        help="label_rules YAML 路径",
    ),
    output_p0: str = typer.Option(
        "data/features/features_pre.parquet",
        help="P0 特征 parquet 输出路径",
    ),
    output_p1: str = typer.Option(
        "data/features/features_post.parquet",
        help="P1 特征 parquet 输出路径",
    ),
) -> None:
    """Build feature matrices for P0 and P1 modeling."""
    import pandas as pd
    from cpet_stage1.features.feature_engineer import FeatureEngineer

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]Step 5: Feature Engineering[/bold blue]")

    cp = (
        Path("data/labels/cohort_registry.parquet")
        if cohort_path == "auto"
        else Path(cohort_path)
    )
    if not cp.exists():
        console.print(f"[red]cohort_registry 不存在: {cp}\n请先运行 'make labels'[/red]")
        raise typer.Exit(1)

    df = pd.read_parquet(cp)
    console.print(f"cohort_registry: {cp} ({len(df)} 行)")

    fe = FeatureEngineer(feature_config, label_rules)

    # P0 特征
    r_p0 = fe.build_p0(df, include_bp=True)
    r_p0.to_parquet(output_p0)
    console.print(f"[green]✓ P0 特征: {output_p0} ({r_p0.X.shape})[/green]")
    console.print(r_p0.summary())

    # P1 特征
    r_p1 = fe.build_p1(df, cycle_only=False)
    r_p1.to_parquet(output_p1)
    console.print(f"[green]✓ P1 特征: {output_p1} ({r_p1.X.shape})[/green]")
    console.print(r_p1.summary())


@app.command()
def anchors(
    cohort_path: str = typer.Option(
        "auto",
        help="cohort_registry parquet 路径，'auto' 则使用 data/labels/cohort_registry.parquet",
    ),
    label_path: str = typer.Option(
        "auto",
        help="label_table parquet 路径，'auto' 则使用 data/labels/label_table.parquet",
    ),
    reference_path: str = typer.Option(
        "auto",
        help="reference_scores parquet 路径，'auto' 则尝试 data/labels/reference_scores.parquet",
    ),
    anchor_rules: str = typer.Option(
        "configs/bridge/anchor_rules_v1.yaml",
        help="anchor_rules YAML 路径",
    ),
    contract_rules: str = typer.Option(
        "configs/bridge/contract_rules_v1.yaml",
        help="bridge contract_rules YAML 路径",
    ),
    output_parquet: str = typer.Option(
        "data/anchors/anchor_table.parquet",
        help="输出 anchor_table parquet 路径",
    ),
    contract_snapshot: str = typer.Option(
        "data/contracts/contract_snapshot.json",
        help="输出 contract_snapshot.json 路径",
    ),
    package_dir: str = typer.Option(
        "outputs/bridge_prep/anchor_package_v1",
        help="可选的 JSON/CSV 格式包输出目录",
    ),
) -> None:
    """Build anchor table (R/T/I axes) and validate bridge contract."""
    import pandas as pd
    from cpet_stage1.anchors.anchor_builder import AnchorBuilder
    from cpet_stage1.anchors.export_anchor_package import export_anchor_package
    from cpet_stage1.contracts.bridge_contract import BridgeContractValidator

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]Step 6: Anchor Export[/bold blue]")

    # 加载 cohort_registry
    cp = (
        Path("data/labels/cohort_registry.parquet")
        if cohort_path == "auto"
        else Path(cohort_path)
    )
    if not cp.exists():
        console.print(f"[red]cohort_registry 不存在: {cp}\n请先运行 'make labels'[/red]")
        raise typer.Exit(1)
    cohort_df = pd.read_parquet(cp)
    console.print(f"cohort_registry: {cp} ({len(cohort_df)} 行)")

    # 加载 label_table（可选）
    lp = (
        Path("data/labels/label_table.parquet")
        if label_path == "auto"
        else Path(label_path)
    )
    label_df = pd.read_parquet(lp) if lp.exists() else None
    if label_df is not None:
        console.print(f"label_table: {lp} ({len(label_df)} 行)")
    else:
        console.print(f"[yellow]⚠ label_table 不存在: {lp}，跳过合并[/yellow]")

    # 加载 reference_scores（可选）
    rp = (
        Path("data/labels/reference_scores.parquet")
        if reference_path == "auto"
        else Path(reference_path)
    )
    reference_df = pd.read_parquet(rp) if rp.exists() else None
    if reference_df is not None:
        console.print(f"reference_scores: {rp} ({len(reference_df)} 行)")

    # 构建锚点表
    builder = AnchorBuilder(anchor_rules)
    result = builder.build(cohort_df, label_df=label_df, reference_df=reference_df)
    console.print(result.summary())

    # 导出锚点包
    exported = export_anchor_package(
        result,
        anchor_parquet_path=output_parquet,
        coverage_report_path=str(Path(output_parquet).parent / "anchor_coverage_report.md"),
        package_dir=package_dir,
    )
    for name, path in exported.items():
        console.print(f"[green]✓ {name}: {path}[/green]")

    # Bridge Contract 验证
    validator = BridgeContractValidator(
        contract_rules_path=contract_rules if Path(contract_rules).exists() else None
    )
    contract_result = validator.validate(result.df)
    console.print(contract_result.report())
    contract_result.save_snapshot(contract_snapshot)
    console.print(
        f"[{'green' if contract_result.passed else 'red'}]"
        f"{'✓' if contract_result.passed else '✗'} contract_snapshot: {contract_snapshot}"
        f"[/{'green' if contract_result.passed else 'red'}]"
    )

    if not contract_result.passed:
        console.print("[red]⚠ Bridge Contract 验证失败，请检查锚点表完整性[/red]")
        raise typer.Exit(1)


model_app = typer.Typer(help="Model training commands")
app.add_typer(model_app, name="model")


@model_app.command("p0")
def model_p0(
    cohort_path: str = typer.Option(
        "auto",
        help="cohort_registry parquet 路径",
    ),
    label_col: str = typer.Option("p0_event", help="P0 标签列名"),
    output_dir: str = typer.Option("outputs/models/p0", help="模型输出目录"),
    report_path: str = typer.Option("reports/p0_model_report.md", help="报告输出路径"),
    n_iter: int = typer.Option(20, help="RandomizedSearchCV 迭代次数"),
    feature_config: str = typer.Option(
        "configs/features/feature_config_v1.yaml",
        help="feature_config YAML 路径（v2 = 扩展特征）",
    ),
    label_rules: str = typer.Option(
        "configs/data/label_rules_v2.yaml",
        help="label_rules YAML 路径（v3 = EIH-clean 版）",
    ),
) -> None:
    """Train P0 baseline models (LASSO + XGBoost, with/without BP)."""
    import pandas as pd
    from cpet_stage1.modeling.train_p0 import P0Trainer
    from cpet_stage1.modeling.plots import generate_all_m5_plots
    from cpet_stage1.modeling.report import ModelReportGenerator

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]Modeling: P0 Safety Event[/bold blue]")

    cp = (
        Path("data/labels/cohort_registry.parquet")
        if cohort_path == "auto"
        else Path(cohort_path)
    )
    if not cp.exists():
        console.print(f"[red]cohort_registry 不存在: {cp}\n请先运行 'make labels'[/red]")
        raise typer.Exit(1)

    df = pd.read_parquet(cp)
    # 合并标签表（p0_event 等列）
    label_p = Path("data/labels/label_table.parquet")
    if label_p.exists():
        lt = pd.read_parquet(label_p)
        for col in lt.columns:
            if col not in df.columns:
                df[col] = lt[col].values
    console.print(f"数据: {cp} ({len(df)} 行)")

    trainer = P0Trainer(feature_config=feature_config, label_rules=label_rules)
    results = trainer.run(df, label_col=label_col, n_iter_override=n_iter)

    # 打印结果摘要
    for model_name, variants in results.items():
        for variant, result in variants.items():
            bm = result.test_metrics.binary_metrics
            console.print(
                f"[green]{model_name} [{variant}]: AUC={bm.auc_roc:.4f}, "
                f"AUPRC={bm.auprc:.4f}, Brier={bm.brier:.4f}[/green]"
            )

    # 生成图表
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        generated = generate_all_m5_plots(p0_results=results, output_dir="reports/figures/m5")
        console.print(f"[green]✓ 图表: {len(generated)} 张[/green]")
    except Exception as e:
        console.print(f"[yellow]图表生成失败（继续）: {e}[/yellow]")

    # 生成报告
    gen = ModelReportGenerator()
    gen.generate_p0_report(results, output_path=report_path)
    console.print(f"[green]✓ P0 报告: {report_path}[/green]")


@model_app.command("p1")
def model_p1(
    cohort_path: str = typer.Option(
        "auto",
        help="cohort_registry parquet 路径",
    ),
    label_col: str = typer.Option("p1_zone", help="P1 标签列名"),
    output_dir: str = typer.Option("outputs/models/p1", help="模型输出目录"),
    report_path: str = typer.Option("reports/p1_model_report.md", help="报告输出路径"),
    n_iter: int = typer.Option(10, help="RandomizedSearchCV 迭代次数"),
    feature_config: str = typer.Option(
        "configs/features/feature_config_v1.yaml",
        help="feature_config YAML 路径（v2 = 扩展特征）",
    ),
    label_rules: str = typer.Option(
        "configs/data/label_rules_v2.yaml",
        help="label_rules YAML 路径（v3 = EIH-clean 版）",
    ),
    lgbm_config: str = typer.Option(
        "configs/model/p1_lgbm.yaml",
        help="LightGBM 超参数配置 YAML 路径（代价敏感版使用 p1_lgbm_cost_sensitive.yaml）",
    ),
    catboost_config: str = typer.Option(
        "configs/model/p1_catboost.yaml",
        help="CatBoost 超参数配置 YAML 路径（代价敏感版使用 p1_catboost_cost_sensitive.yaml）",
    ),
) -> None:
    """Train P1 zone classification models (OrdinalLogistic + LightGBM + CatBoost)."""
    import pandas as pd
    from cpet_stage1.modeling.train_p1 import P1Trainer
    from cpet_stage1.modeling.plots import generate_all_m5_plots
    from cpet_stage1.modeling.report import ModelReportGenerator

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]Modeling: P1 Zone Classification[/bold blue]")

    cp = (
        Path("data/labels/cohort_registry.parquet")
        if cohort_path == "auto"
        else Path(cohort_path)
    )
    if not cp.exists():
        console.print(f"[red]cohort_registry 不存在: {cp}\n请先运行 'make labels'[/red]")
        raise typer.Exit(1)

    df = pd.read_parquet(cp)
    # 合并标签表（p1_zone 等列）
    label_p = Path("data/labels/label_table.parquet")
    if label_p.exists():
        lt = pd.read_parquet(label_p)
        for col in lt.columns:
            if col not in df.columns:
                df[col] = lt[col].values
    console.print(f"数据: {cp} ({len(df)} 行)")

    trainer = P1Trainer(
        feature_config=feature_config,
        label_rules=label_rules,
        lgbm_config=lgbm_config,
        catboost_config=catboost_config,
    )
    results = trainer.run(df, label_col=label_col, n_iter_override=n_iter)

    # 打印结果摘要
    for model_name, variants in results.items():
        for variant, result in variants.items():
            mc = result.test_metrics.multiclass_metrics
            if mc:
                console.print(
                    f"[green]{model_name} [{variant}]: F1_macro={mc.f1_macro:.4f}, "
                    f"kappa={mc.kappa_weighted:.4f}[/green]"
                )

    # 生成图表
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        generated = generate_all_m5_plots(p1_results=results, output_dir="reports/figures/m5")
        console.print(f"[green]✓ 图表: {len(generated)} 张[/green]")
    except Exception as e:
        console.print(f"[yellow]图表生成失败（继续）: {e}[/yellow]")

    # 生成报告
    gen = ModelReportGenerator()
    gen.generate_p1_report(results, output_path=report_path)
    console.print(f"[green]✓ P1 报告: {report_path}[/green]")


@model_app.command("evaluate")
def model_evaluate(
    cohort_path: str = typer.Option("auto", help="cohort_registry parquet 路径"),
) -> None:
    """Evaluate trained models (requires previous model run)."""
    console.print("[bold blue]Modeling: Evaluate[/bold blue]")
    console.print("[yellow]请先运行 'make model-p0' 和 'make model-p1'[/yellow]")


@model_app.command("interpret")
def model_interpret(
    cohort_path: str = typer.Option("auto", help="cohort_registry parquet 路径"),
    output_dir: str = typer.Option("reports/figures/m5", help="SHAP 图表输出目录"),
    n_iter: int = typer.Option(10, help="RandomizedSearchCV 迭代次数（快速重训）"),
    max_shap_samples: int = typer.Option(200, help="SHAP 计算最大样本数"),
) -> None:
    """Run SHAP interpretation: retrain P0/P1 inline and generate SHAP figures."""
    import pandas as pd
    from cpet_stage1.modeling.train_p0 import P0Trainer
    from cpet_stage1.modeling.train_p1 import P1Trainer
    from cpet_stage1.modeling.interpret import SHAPInterpreter

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]Modeling: SHAP Interpretation[/bold blue]")

    # 加载数据
    cp = (
        Path("data/labels/cohort_registry.parquet")
        if cohort_path == "auto"
        else Path(cohort_path)
    )
    if not cp.exists():
        console.print(f"[red]cohort_registry 不存在: {cp}\n请先运行 'make labels'[/red]")
        raise typer.Exit(1)

    df = pd.read_parquet(cp)
    label_p = Path("data/labels/label_table.parquet")
    if label_p.exists():
        lt = pd.read_parquet(label_p)
        for col in lt.columns:
            if col not in df.columns:
                df[col] = lt[col].values
    console.print(f"数据: {len(df)} 行")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    interpreter = SHAPInterpreter()
    all_generated = []

    # --- P0 SHAP (XGBoost, no_bp 变体——最稳健) ---
    console.print("\n[bold]P0 模型重训 + SHAP[/bold]")
    try:
        p0_trainer = P0Trainer()
        p0_results = p0_trainer.run(df, label_col="p0_event", n_iter_override=n_iter)

        for variant in ["no_bp", "with_bp"]:
            xgb_res = p0_results.get("xgb", {}).get(variant)
            if xgb_res is None:
                continue
            model = xgb_res.calibrated_model
            X_shap = xgb_res.feature_result.X  # 训练集特征（已拟合的 imputer/scaler）
            feat_names = xgb_res.feature_result.feature_names
            if X_shap is None or len(X_shap) == 0:
                continue
            try:
                result = interpreter.explain(
                    model, X_shap, model_type="tree", task="p0",
                    model_name="XGBoost", variant=variant,
                    feature_names=feat_names, max_samples=max_shap_samples,
                )
                generated = interpreter.save_plots(result, X_shap, output_dir=out_dir)
                all_generated.extend(generated)
                console.print(f"[green]✓ P0 XGBoost [{variant}] SHAP: {len(generated)} 张[/green]")
            except Exception as e:
                console.print(f"[yellow]P0 XGBoost [{variant}] SHAP 失败: {e}[/yellow]")
    except Exception as e:
        console.print(f"[yellow]P0 重训失败: {e}[/yellow]")

    # --- P1 SHAP (LightGBM, full 变体) ---
    console.print("\n[bold]P1 模型重训 + SHAP[/bold]")
    try:
        p1_trainer = P1Trainer()
        p1_results = p1_trainer.run(df, label_col="p1_zone", n_iter_override=n_iter)

        for variant in ["full", "cycle_only"]:
            lgbm_res = p1_results.get("lgbm", {}).get(variant)
            if lgbm_res is None:
                continue
            model = lgbm_res.calibrated_model
            X_shap = lgbm_res.feature_result.X  # 训练集特征
            feat_names = lgbm_res.feature_result.feature_names
            if X_shap is None or len(X_shap) == 0:
                continue
            try:
                result = interpreter.explain(
                    model, X_shap, model_type="tree", task="p1",
                    model_name="LightGBM", variant=variant,
                    feature_names=feat_names, max_samples=max_shap_samples,
                )
                generated = interpreter.save_plots(result, X_shap, output_dir=out_dir)
                all_generated.extend(generated)
                console.print(f"[green]✓ P1 LightGBM [{variant}] SHAP: {len(generated)} 张[/green]")
            except Exception as e:
                console.print(f"[yellow]P1 LightGBM [{variant}] SHAP 失败: {e}[/yellow]")
    except Exception as e:
        console.print(f"[yellow]P1 重训失败: {e}[/yellow]")

    console.print(f"\n[bold green]✓ SHAP 解释完成: {len(all_generated)} 张图表 → {out_dir}[/bold green]")
    for fp in all_generated:
        console.print(f"  {fp}")


@model_app.command("report")
def model_report(
    p0_report: str = typer.Option("reports/p0_model_report.md", help="P0 报告路径"),
    p1_report: str = typer.Option("reports/p1_model_report.md", help="P1 报告路径"),
) -> None:
    """Generate model reports."""
    console.print("[bold blue]Modeling: Report Generation[/bold blue]")
    for rp in [p0_report, p1_report]:
        if Path(rp).exists():
            console.print(f"[green]✓ {rp}[/green]")
        else:
            console.print(f"[yellow]⚠ {rp} 不存在，请先运行模型训练[/yellow]")


@model_app.command("outcome")
def model_outcome(
    cohort_path: str = typer.Option(
        "auto",
        help="cohort_registry parquet 路径",
    ),
    label_path: str = typer.Option(
        "auto",
        help="label_table parquet 路径，'auto' 则使用 data/labels/label_table.parquet",
    ),
    config: str = typer.Option(
        "configs/model/outcome_lgbm.yaml",
        help="结局锚定模型配置 YAML 路径",
    ),
    report_path: str = typer.Option(
        "reports/outcome_model_report.md",
        help="报告输出路径",
    ),
    output_zone_parquet: str = typer.Option(
        "data/labels/outcome_zone.parquet",
        help="输出 outcome_zone parquet（含 outcome_zone 列）路径",
    ),
    n_iter: int = typer.Option(40, help="RandomizedSearchCV 迭代次数"),
) -> None:
    """Phase G Method 1：结局锚定安全区模型（直接预测 test_result）。"""
    import pandas as pd
    from cpet_stage1.modeling.train_outcome import OutcomeTrainer

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]Phase G Method 1: 结局锚定安全区模型[/bold blue]")

    cp = (
        Path("data/labels/cohort_registry.parquet")
        if cohort_path == "auto"
        else Path(cohort_path)
    )
    if not cp.exists():
        console.print(f"[red]cohort_registry 不存在: {cp}\n请先运行 'make labels'[/red]")
        raise typer.Exit(1)

    df = pd.read_parquet(cp)

    # 合并 label_table（含 test_result 等列）
    lp = (
        Path("data/labels/label_table.parquet")
        if label_path == "auto"
        else Path(label_path)
    )
    if lp.exists():
        lt = pd.read_parquet(lp)
        for col in lt.columns:
            if col not in df.columns:
                df[col] = lt[col].values
        console.print(f"label_table: {lp} ({len(lt)} 行)")

    console.print(f"数据: {cp} ({len(df)} 行)")

    # 检查 test_result 列
    if "test_result" not in df.columns:
        console.print("[red]test_result 列不存在，请检查 label_table 是否已生成[/red]")
        raise typer.Exit(1)

    trainer = OutcomeTrainer(config_path=config)
    result = trainer.run(df, outcome_col="test_result", n_iter_override=n_iter)

    console.print(
        f"[green]CV AUC: {result.cv_auc_mean:.3f} ± {result.cv_auc_std:.3f}[/green]"
    )
    console.print(
        f"[green]测试集: AUC={result.test_auc:.3f}, AP={result.test_ap:.3f}, "
        f"Brier={result.test_brier:.3f}[/green]"
    )
    for z in ["green", "yellow", "red"]:
        info = result.zone_distribution.get(z, {})
        console.print(
            f"  {z.capitalize()}: {info.get('n', 0)} ({info.get('pct', 0):.1f}%)"
        )

    # 保存报告
    report_str = trainer.generate_report(result)
    out_path = Path(report_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report_str, encoding="utf-8")
    console.print(f"[green]✓ 结局锚定模型报告: {report_path}[/green]")

    # 保存 outcome_zone parquet（供 concordance 使用）
    if result.cutpoints is not None and not result.zone_distribution == {}:
        # 重新生成全数据 outcome_zone 列并保存
        from cpet_stage1.labels.outcome_zone import (
            assign_outcome_zones_series,
        )
        import numpy as np
        if result.calibrated_model is not None and "test_result" in df.columns:
            from cpet_stage1.modeling.train_outcome import _prepare_features
            feat_names = trainer._feature_names
            X_all = _prepare_features(df, feat_names)
            # 用训练集中位数填充（近似，因无法访问原始 X_train）
            X_all_filled = X_all.fillna(X_all.median())
            try:
                y_proba_all = result.calibrated_model.predict_proba(X_all_filled)[:, 1]
                y_proba_series = pd.Series(y_proba_all, index=df.index)
                zone_series = assign_outcome_zones_series(y_proba_series, result.cutpoints)
                zone_df = pd.DataFrame(
                    {"subject_id": df.get("subject_id", df.index), "outcome_zone": zone_series}
                )
                oz_path = Path(output_zone_parquet)
                oz_path.parent.mkdir(parents=True, exist_ok=True)
                zone_df.to_parquet(oz_path, index=False)
                console.print(f"[green]✓ outcome_zone parquet: {output_zone_parquet}[/green]")
            except Exception as e:
                console.print(f"[yellow]outcome_zone parquet 生成失败（继续）: {e}[/yellow]")


@stats_app.command("anomaly")
def stats_anomaly(
    cohort_path: str = typer.Option(_DEFAULT_COHORT_PARQUET, help="cohort_registry parquet 路径"),
    config: str = typer.Option(
        "configs/stats/anomaly_config.yaml",
        help="anomaly 配置 YAML 路径",
    ),
    reference_flag_col: str = typer.Option(
        "reference_flag_wide",
        help="参考人群标志列名",
    ),
    report_path: str = typer.Option(
        "reports/anomaly_score_report.md",
        help="报告输出路径",
    ),
    output_zone_parquet: str = typer.Option(
        "data/labels/anomaly_zone.parquet",
        help="输出 anomaly_zone parquet（含 anomaly_zone + mahal_d2 列）路径",
    ),
) -> None:
    """Phase G Method 2：多变量异常评分（Mahalanobis 距离）。"""
    import pandas as pd
    from cpet_stage1.stats.anomaly_score import run_anomaly_scoring, generate_anomaly_report

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]Phase G Method 2: 多变量异常评分（Mahalanobis D²）[/bold blue]")

    df = _load_cohort_df(cohort_path)

    # 合并 label_table（获取 test_result）
    lp = Path("data/labels/label_table.parquet")
    if lp.exists():
        lt = pd.read_parquet(lp)
        for col in lt.columns:
            if col not in df.columns:
                df[col] = lt[col].values

    console.print(f"数据: {cohort_path} ({len(df)} 行)")

    result = run_anomaly_scoring(
        df,
        config_path=config,
        reference_flag_col=reference_flag_col,
        outcome_col="test_result" if "test_result" in df.columns else None,
    )

    console.print(
        f"[green]有效样本: {result.n_valid}, 排除: {result.n_missing_excluded}[/green]"
    )
    for z in ["green", "yellow", "red"]:
        info = result.zone_distribution.get(z, {})
        console.print(
            f"  {z.capitalize()}: {info.get('n', 0)} ({info.get('pct', 0):.1f}%)"
        )
    if result.correlation_with_outcome is not None:
        console.print(f"[green]D² vs test_result 相关: r={result.correlation_with_outcome:.3f}[/green]")

    # 保存报告
    report_str = generate_anomaly_report(result)
    out_path = Path(report_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report_str, encoding="utf-8")
    console.print(f"[green]✓ 异常评分报告: {report_path}[/green]")

    # 保存 anomaly_zone parquet（供 concordance 使用）
    if not result.scores.empty:
        zone_df = result.scores[["mahal_d2", "anomaly_zone"]].copy()
        if "subject_id" in df.columns:
            zone_df.insert(0, "subject_id", df["subject_id"].values)
        az_path = Path(output_zone_parquet)
        az_path.parent.mkdir(parents=True, exist_ok=True)
        zone_df.to_parquet(az_path, index=True)
        console.print(f"[green]✓ anomaly_zone parquet: {output_zone_parquet}[/green]")


@stats_app.command("concordance")
def stats_concordance(
    cohort_path: str = typer.Option(_DEFAULT_COHORT_PARQUET, help="cohort_registry parquet 路径"),
    config: str = typer.Option(
        "configs/data/concordance_config.yaml",
        help="concordance 配置 YAML 路径",
    ),
    report_path: str = typer.Option(
        "reports/concordance_report.md",
        help="报告输出路径",
    ),
    outcome_zone_parquet: str = typer.Option(
        "data/labels/outcome_zone.parquet",
        help="Method 1 outcome_zone parquet 路径",
    ),
    anomaly_zone_parquet: str = typer.Option(
        "data/labels/anomaly_zone.parquet",
        help="Method 2 anomaly_zone parquet 路径",
    ),
) -> None:
    """Phase G Method 3：多定义一致性框架（K 定义投票）。"""
    import pandas as pd
    from cpet_stage1.labels.concordance_ensemble import (
        run_concordance_analysis,
        generate_concordance_report,
    )

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]Phase G Method 3: 多定义一致性框架[/bold blue]")

    df = _load_cohort_df(cohort_path)

    # 合并各安全区定义
    for extra_path, zone_col in [
        ("data/labels/label_table.parquet", None),
        ("data/labels/zone_table.parquet", None),
        ("data/labels/zone_table_v2.parquet", None),
        (outcome_zone_parquet, "outcome_zone"),
        (anomaly_zone_parquet, "anomaly_zone"),
    ]:
        ep = Path(extra_path)
        if ep.exists():
            extra = pd.read_parquet(ep)
            for col in extra.columns:
                if col not in df.columns:
                    try:
                        df[col] = extra[col].values
                    except Exception:
                        pass

    console.print(f"数据: {cohort_path} ({len(df)} 行)")
    console.print(f"可用列: {[c for c in ['p1_zone', 'z_lab_v2', 'outcome_zone', 'anomaly_zone', 'vo2_zone_simple'] if c in df.columns]}")

    result = run_concordance_analysis(
        df,
        config_path=config,
        outcome_col="test_result" if "test_result" in df.columns else None,
    )

    hc = result.high_confidence_stats
    console.print(
        f"[green]高信度: {hc.get('n_high_confidence', 0)} ({hc.get('pct_high_confidence', 0):.1f}%), "
        f"不确定: {hc.get('n_uncertain', 0)} ({hc.get('pct_uncertain', 0):.1f}%)[/green]"
    )
    console.print(f"  Green/Red 冲突: {hc.get('n_green_red_conflict', 0)}")

    # 保存报告
    report_str = generate_concordance_report(result)
    out_path = Path(report_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report_str, encoding="utf-8")
    console.print(f"[green]✓ 一致性框架报告: {report_path}[/green]")


@app.command()
def reports(
    reports_dir: str = typer.Option("reports", help="reports 目录路径"),
    output: str = typer.Option("reports/summary_report.md", help="聚合摘要输出路径"),
) -> None:
    """扫描已有报告并生成 summary_report.md。"""
    from cpet_stage1.reporting import ReportAggregator

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]M7: Report Aggregation[/bold blue]")

    aggregator = ReportAggregator(reports_dir=reports_dir)
    manifest = aggregator.scan()

    # 显示扫描结果
    console.print(f"\n[bold]报告扫描结果[/bold]（{manifest.scan_time}）")
    console.print(f"  找到报告：{len(manifest.found_reports)} 个")
    console.print(f"  缺失报告：{len(manifest.missing_reports)} 个")
    console.print(f"  图表合计：{manifest.total_figures} 张")

    if manifest.missing_reports:
        console.print("\n[yellow]缺失报告：[/yellow]")
        for m in manifest.missing_reports:
            console.print(f"  [yellow]⚠ {m}[/yellow]")
    else:
        console.print("[green]✓ 所有预期报告均存在[/green]")

    # 生成摘要
    out_path = aggregator.generate_summary(manifest, output_path=output)
    console.print(f"\n[green]✓ 聚合摘要: {out_path}[/green]")


@app.command(name="bridge-prep")
def bridge_prep(
    output_dir: str = typer.Option(
        "outputs/bridge_prep",
        help="输出目录",
    ),
    anchor_rules: str = typer.Option(
        "configs/bridge/anchor_rules_v1.yaml",
        help="anchor_rules YAML 路径",
    ),
    bridge_sampling: str = typer.Option(
        "configs/bridge/bridge_sampling_priority_v0.yaml",
        help="bridge_sampling_priority YAML 路径",
    ),
    home_proxy_map: str = typer.Option(
        "configs/bridge/home_proxy_map_v0.yaml",
        help="home_proxy_map YAML 路径",
    ),
    question_list_source: str = typer.Option(
        "docs/bridge/bridge_question_list_v1.md",
        help="桥接问题清单源文件路径",
    ),
) -> None:
    """Generate Stage II bridge prep package (anchor dict + proxy table + sampling priority + question list)."""
    from cpet_stage1.bridge_prep.export_bridge_prep import export_bridge_prep_package

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]Bridge Preparation[/bold blue]")

    exported = export_bridge_prep_package(
        output_dir=output_dir,
        anchor_rules_path=anchor_rules,
        bridge_sampling_path=bridge_sampling,
        home_proxy_map_path=home_proxy_map,
        question_list_source=question_list_source,
    )

    for name, path in exported.items():
        console.print(f"[green]✓ {name}: {path}[/green]")

    console.print(
        f"\n[bold green]Bridge Prep 包已生成：{output_dir} ({len(exported)} 个文件)[/bold green]"
    )


@app.command()
def release(
    reports_dir: str = typer.Option("reports", help="reports 目录路径"),
    release_dir: str = typer.Option("reports/release", help="发布包输出目录"),
    version: str = typer.Option("v1.0.0-stage1", help="版本号"),
    no_bridge_prep: bool = typer.Option(False, help="跳过复制 bridge_prep"),
    bridge_prep_dir: str = typer.Option("outputs/bridge_prep", help="bridge_prep 源目录"),
) -> None:
    """打包冻结发布包（报告 + 图表 + 配置快照 + 指标 + bridge_prep）。"""
    from cpet_stage1.reporting import ReportAggregator, ReleasePackager

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]M7: Release Packaging[/bold blue]")

    aggregator = ReportAggregator(reports_dir=reports_dir)
    manifest = aggregator.scan()

    # 先生成 summary（如尚未生成）
    summary_path = Path(reports_dir) / "summary_report.md"
    if not summary_path.exists():
        aggregator.generate_summary(manifest, output_path=summary_path)
        console.print(f"[dim]✓ 已生成 summary_report.md[/dim]")
        # 重新扫描以包含 summary
        manifest = aggregator.scan()

    packager = ReleasePackager(version=version)
    result = packager.package(
        manifest=manifest,
        release_dir=release_dir,
        include_bridge_prep=not no_bridge_prep,
        bridge_prep_dir=bridge_prep_dir,
    )

    console.print(f"\n[bold green]发布包已生成[/bold green]")
    console.print(f"  版本：{result.version}")
    console.print(f"  目录：{result.release_dir}")
    console.print(f"  文件数：{result.file_count}")
    console.print(f"  manifest：{result.manifest_path}")

    if result.metrics:
        console.print("\n[bold]关键指标摘要[/bold]")
        for task, m in result.metrics.items():
            console.print(f"  {task.upper()}: {m}")

    console.print(f"\n[green]✓ release_manifest.json: {result.manifest_path}[/green]")


# ─────────────────────────────────────────────────────
# Stage 1B 共享预处理辅助函数
# ─────────────────────────────────────────────────────

def _derive_stage1b_columns(df: "pd.DataFrame") -> "pd.DataFrame":
    """派生 Stage 1B 管线所需的衍生列（bmi / protocol_mode / eih_status）。

    在各 Stage 1B handler 加载 staging parquet 之后调用，确保下游模块
    不会因缺失列而报错。仅在列不存在时派生，不会覆盖已有值。
    """
    import pandas as pd  # noqa: PLC0415

    # 1. bmi：由 height_cm / weight_kg 计算
    if "bmi" not in df.columns:
        if "height_cm" in df.columns and "weight_kg" in df.columns:
            height_m = df["height_cm"] / 100.0
            df = df.copy()
            df["bmi"] = df["weight_kg"] / (height_m ** 2)

    # 2. protocol_mode：从协议布尔列推断
    if "protocol_mode" not in df.columns:
        df = df.copy() if not isinstance(df, pd.DataFrame) else df.copy()

        def _infer_mode(row: "pd.Series") -> str:
            if row.get("protocol_cycle", False):
                return "cycle"
            if row.get("protocol_bruce", False) or row.get("protocol_modified_bruce", False):
                return "treadmill"
            return "treadmill"  # 缺省：跑步机

        df["protocol_mode"] = df.apply(_infer_mode, axis=1)

    # 3. eih_status：从 group_code 推断
    if "eih_status" not in df.columns:
        if "group_code" in df.columns:
            df = df.copy() if "bmi" not in df.columns else df  # 可能已经 copy 过
            df["eih_status"] = df["group_code"].str.contains("EIH", na=False)
        elif "cohort_2x2" in df.columns:
            df["eih_status"] = df["cohort_2x2"].str.contains("EIH", na=False)
        else:
            df["eih_status"] = False

    return df


@stats_app.command("confidence")
def stats_confidence(
    staging: str = typer.Option(
        "data/staging/cpet_staging_v1.parquet",
        help="staging parquet 路径",
    ),
    instability_parquet: str = typer.Option(
        "data/features/instability_stage1b.parquet",
        help="instability parquet（由 stats instability 生成）",
    ),
    zone_rules: str = typer.Option(
        "configs/data/zone_rules_stage1b.yaml",
        help="zone_rules_stage1b.yaml 路径",
    ),
    variable_roles: str = typer.Option(
        "configs/data/variable_roles_stage1b.yaml",
        help="variable_roles_stage1b.yaml 路径",
    ),
    output_parquet: str = typer.Option(
        "data/features/confidence_stage1b.parquet",
        help="输出 parquet 路径",
    ),
    report_output: str = typer.Option(
        "reports/confidence_report.md",
        help="报告输出路径",
    ),
) -> None:
    """Stage 1B — 置信度引擎（completeness/effort/anchor/validation → confidence/indeterminate）"""
    import pandas as pd

    from cpet_stage1.anchors.confidence_engine import (
        generate_confidence_report,
        run_confidence_engine,
    )

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]Stage 1B: Confidence Engine[/bold blue]")

    staging_path = Path(staging)
    inst_path = Path(instability_parquet)

    if not staging_path.exists():
        console.print(f"[red]staging 不存在: {staging_path}[/red]")
        raise typer.Exit(1)
    if not inst_path.exists():
        console.print(f"[red]instability parquet 不存在: {inst_path}[/red]")
        raise typer.Exit(1)

    df = pd.read_parquet(staging_path)
    df = _derive_stage1b_columns(df)
    inst_df = pd.read_parquet(inst_path)

    zone_col = "final_zone_before_confidence"
    severe_col = "instability_severe"
    if zone_col not in inst_df.columns or severe_col not in inst_df.columns:
        console.print(f"[red]缺少必要列: {zone_col} / {severe_col}[/red]")
        raise typer.Exit(1)

    zone_before = inst_df[zone_col].reindex(df.index)
    severe = inst_df[severe_col].reindex(df.index).fillna(False)

    result = run_confidence_engine(
        df, zone_before, severe,
        cfg_path=zone_rules,
        variable_roles_path=variable_roles,
    )
    console.print(result.summary())

    out_df = inst_df.copy()
    for col in result.df.columns:
        out_df[col] = result.df[col]
    Path(output_parquet).parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(output_parquet)
    console.print(f"[green]✓ output: {output_parquet}[/green]")

    report = generate_confidence_report(result, df_original=df, output_path=report_output)
    console.print(f"[green]✓ report: {report_output}[/green]")


@stats_app.command("reference-quantiles")
def stats_reference_quantiles(
    staging: str = typer.Option(
        "data/staging/cpet_staging_v1.parquet",
        help="staging parquet 路径",
    ),
    spec: str = typer.Option(
        "configs/data/reference_spec_stage1b.yaml",
        help="reference_spec_stage1b.yaml 路径",
    ),
    use_strict: bool = typer.Option(
        True,
        help="True=使用 strict 参考子集；False=使用 wide",
    ),
    bundle_output: str = typer.Option(
        "outputs/reference_models/quantile_bundle_stage1b.joblib",
        help="分位模型 bundle 输出路径",
    ),
    predictions_output: str = typer.Option(
        "data/features/reference_quantiles_stage1b.parquet",
        help="全量预测分位 parquet 输出路径",
    ),
    report_output: str = typer.Option(
        "reports/reference_quantiles_report.md",
        help="参考分位报告输出路径",
    ),
) -> None:
    """Stage 1B — 条件分位参考模型（QuantileRegressor + age样条）"""
    import pandas as pd

    from cpet_stage1.stats.reference_quantiles import (
        QuantileBundleSet,
        build_reference_subset_stage1b,
        fit_bundle_set,
        generate_reference_quantiles_report,
        load_reference_spec,
    )

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]Stage 1B: Reference Quantile Models[/bold blue]")

    # 加载数据
    staging_path = Path(staging)
    if not staging_path.exists():
        console.print(f"[red]staging parquet 不存在: {staging_path}[/red]")
        raise typer.Exit(1)
    df = pd.read_parquet(staging_path)
    df = _derive_stage1b_columns(df)
    console.print(f"  数据: {len(df)} 行 × {df.shape[1]} 列")

    # 加载 spec
    spec_cfg = load_reference_spec(spec)

    # 构建参考子集
    df = build_reference_subset_stage1b(df, spec_cfg)
    flag_col = "reference_flag_strict" if use_strict else "reference_flag_wide"
    ref_mask = df[flag_col]
    df_ref = df[ref_mask]
    console.print(f"  参考子集（{flag_col}）: {len(df_ref)} 行")

    # 获取目标变量
    target_vars = [
        v["field"] for v in spec_cfg.get("target_variables", [])
        if v["field"] in df.columns
    ]
    console.print(f"  目标变量: {target_vars}")

    # 拟合分位模型
    qcfg = spec_cfg.get("quantile_model", {})
    bset = fit_bundle_set(
        df_ref,
        target_vars,
        numeric_columns=qcfg.get("covariates", {}).get("numeric", ["age", "bmi"]),
        categorical_columns=qcfg.get("covariates", {}).get("categorical", ["sex", "protocol_mode"]),
        quantiles=qcfg.get("quantiles", [0.10, 0.25, 0.50, 0.75, 0.90]),
        alpha=qcfg.get("alpha", 0.001),
        age_spline_knots=qcfg.get("age_spline_knots", 5),
        min_reference_n=qcfg.get("min_reference_n", 100),
    )
    console.print(f"  已拟合变量: {list(bset.bundles.keys())}")

    # 保存 bundle
    bset.save(bundle_output)
    console.print(f"[green]✓ bundle: {bundle_output}[/green]")

    # 全量预测
    preds = bset.predict(df)
    Path(predictions_output).parent.mkdir(parents=True, exist_ok=True)
    preds.to_parquet(predictions_output)
    console.print(f"[green]✓ predictions: {predictions_output}[/green]")

    # 生成报告
    report = generate_reference_quantiles_report(
        bset, df, reference_mask=ref_mask, output_path=report_output
    )
    console.print(f"[green]✓ report: {report_output}[/green]")
    console.print(f"\n{report[:800]}")

    # 导出参考子集标记（P7）
    ref_subset_output = Path("data/cohort/reference_subset_stage1b.parquet")
    ref_subset_output.parent.mkdir(parents=True, exist_ok=True)
    flag_cols = [c for c in ["reference_flag_strict", "reference_flag_wide"] if c in df.columns]
    df[flag_cols].to_parquet(ref_subset_output)
    console.print(f"[green]✓ 参考子集标记: {ref_subset_output}[/green]")


@stats_app.command("instability")
def stats_instability(
    staging: str = typer.Option(
        "data/staging/cpet_staging_v1.parquet",
        help="staging parquet 路径",
    ),
    phenotype_parquet: str = typer.Option(
        "data/features/phenotype_burden_stage1b.parquet",
        help="phenotype burden parquet（由 stats phenotype 生成）",
    ),
    zone_rules: str = typer.Option(
        "configs/data/zone_rules_stage1b.yaml",
        help="zone_rules_stage1b.yaml 路径",
    ),
    output_parquet: str = typer.Option(
        "data/features/instability_stage1b.parquet",
        help="输出 parquet 路径",
    ),
    report_output: str = typer.Option(
        "reports/instability_report.md",
        help="报告输出路径",
    ),
) -> None:
    """Stage 1B — 不稳定覆盖规则引擎（severe/mild → final_zone_before_confidence）"""
    import pandas as pd

    from cpet_stage1.anchors.instability_rules import (
        generate_instability_report,
        run_instability_engine,
    )

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]Stage 1B: Instability Override Engine[/bold blue]")

    staging_path = Path(staging)
    phenotype_path = Path(phenotype_parquet)

    if not staging_path.exists():
        console.print(f"[red]staging 不存在: {staging_path}[/red]")
        raise typer.Exit(1)
    if not phenotype_path.exists():
        console.print(f"[red]phenotype parquet 不存在: {phenotype_path}[/red]")
        raise typer.Exit(1)

    df = pd.read_parquet(staging_path)
    df = _derive_stage1b_columns(df)
    phen_df = pd.read_parquet(phenotype_path)

    if "phenotype_zone" not in phen_df.columns:
        console.print("[red]phenotype_zone 列不存在[/red]")
        raise typer.Exit(1)

    phenotype_zone = phen_df["phenotype_zone"].reindex(df.index)
    result = run_instability_engine(df, phenotype_zone, cfg_path=zone_rules)
    console.print(result.summary())

    out_df = phen_df.copy()
    for col in result.df.columns:
        out_df[col] = result.df[col]
    Path(output_parquet).parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(output_parquet)
    console.print(f"[green]✓ output: {output_parquet}[/green]")

    report = generate_instability_report(result, df_original=df, output_path=report_output)
    console.print(f"[green]✓ report: {report_output}[/green]")


@stats_app.command("phenotype")
def stats_phenotype(
    staging: str = typer.Option(
        "data/staging/cpet_staging_v1.parquet",
        help="staging parquet 路径",
    ),
    quantiles_parquet: str = typer.Option(
        "data/features/reference_quantiles_stage1b.parquet",
        help="reference quantiles 预测 parquet（由 stats reference-quantiles 生成）",
    ),
    spec: str = typer.Option(
        "configs/data/reference_spec_stage1b.yaml",
        help="reference_spec_stage1b.yaml 路径",
    ),
    zone_rules: str = typer.Option(
        "configs/data/zone_rules_stage1b.yaml",
        help="zone_rules_stage1b.yaml 路径",
    ),
    use_strict: bool = typer.Option(True, help="True=strict 参考子集；False=wide"),
    output_parquet: str = typer.Option(
        "data/features/phenotype_burden_stage1b.parquet",
        help="输出表型负担 parquet 路径",
    ),
    report_output: str = typer.Option(
        "reports/phenotype_burden_report.md",
        help="报告输出路径",
    ),
) -> None:
    """Stage 1B — 表型负担引擎（reserve/ventilatory 双域 + phenotype zone）"""
    import pandas as pd

    from cpet_stage1.anchors.phenotype_engine import (
        generate_phenotype_report,
        load_variable_specs_from_yaml,
        run_phenotype_engine,
    )
    from cpet_stage1.stats.reference_quantiles import (
        build_reference_subset_stage1b,
        load_reference_spec,
    )

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]Stage 1B: Phenotype Burden Engine[/bold blue]")

    df = pd.read_parquet(staging)
    df = _derive_stage1b_columns(df)
    console.print(f"  数据: {len(df)} 行")

    # 加载 reference spec，构建参考 mask
    spec_cfg = load_reference_spec(spec)
    df = build_reference_subset_stage1b(df, spec_cfg)
    flag_col = "reference_flag_strict" if use_strict else "reference_flag_wide"
    ref_mask = df[flag_col]
    console.print(f"  参考子集（{flag_col}）: {ref_mask.sum()} 行")

    # 加载 quantiles
    q_path = Path(quantiles_parquet)
    if not q_path.exists():
        console.print(f"[red]quantiles parquet 不存在: {q_path}[/red]")
        raise typer.Exit(1)
    quantiles = pd.read_parquet(q_path)
    quantiles = quantiles.reindex(df.index)

    # 加载变量规格
    variable_specs = load_variable_specs_from_yaml(zone_rules)
    console.print(f"  变量规格: {len(variable_specs)} 个")

    # 运行表型引擎
    result = run_phenotype_engine(df, quantiles, variable_specs, ref_mask)
    console.print(result.summary())

    # 保存输出
    out_df = df.copy()
    for col in result.df.columns:
        out_df[col] = result.df[col]
    Path(output_parquet).parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(output_parquet)
    console.print(f"[green]✓ output: {output_parquet}[/green]")

    # 生成报告
    report = generate_phenotype_report(result, df_original=df, output_path=report_output)
    console.print(f"[green]✓ report: {report_output}[/green]")


@stats_app.command("outcome-anchor")
def stats_outcome_anchor(
    staging: str = typer.Option(
        "data/staging/cpet_staging_v1.parquet",
        help="staging parquet 路径",
    ),
    output_parquet: str = typer.Option(
        "data/features/outcome_anchor_stage1b.parquet",
        help="输出预测 parquet 路径",
    ),
    report_output: str = typer.Option(
        "reports/outcome_anchor_report.md",
        help="报告输出路径",
    ),
    n_splits: int = typer.Option(5, help="CV folds"),
    model_type: str = typer.Option("elastic_net", help="elastic_net 或 lightgbm"),
) -> None:
    """Stage 1B — Outcome-Anchor 验证模型（test_result 预测，仅用于构念效度验证）"""
    import pandas as pd

    from cpet_stage1.modeling.train_outcome_anchor import (
        generate_outcome_anchor_report,
        run_outcome_anchor,
    )

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]Stage 1B: Outcome-Anchor Validator[/bold blue]")

    staging_path = Path(staging)
    if not staging_path.exists():
        console.print(f"[red]staging 不存在: {staging_path}[/red]")
        raise typer.Exit(1)

    df = pd.read_parquet(staging_path)
    df = _derive_stage1b_columns(df)
    console.print(f"  数据: {len(df)} 行")

    result = run_outcome_anchor(df, n_splits=n_splits, model_type=model_type)
    console.print(f"  CV AUC: {result.cv_auc_mean:.3f} ± {result.cv_auc_std:.3f}")
    console.print(f"  Test AUC: {result.test_auc:.3f}")

    if result.predictions_df is not None:
        Path(output_parquet).parent.mkdir(parents=True, exist_ok=True)
        result.predictions_df.to_parquet(output_parquet)
        console.print(f"[green]✓ predictions: {output_parquet}[/green]")

    report = generate_outcome_anchor_report(result, output_path=report_output)
    console.print(f"[green]✓ report: {report_output}[/green]")


@stats_app.command("anomaly-audit")
def stats_anomaly_audit(
    staging: str = typer.Option(
        "data/staging/cpet_staging_v1.parquet",
        help="staging parquet 路径",
    ),
    output_parquet: str = typer.Option(
        "data/features/anomaly_audit_stage1b.parquet",
        help="输出 parquet 路径",
    ),
    report_output: str = typer.Option(
        "reports/anomaly_audit_report.md",
        help="报告输出路径",
    ),
) -> None:
    """Stage 1B — Anomaly Audit（Robust Mahalanobis QC，不用于 zone 定义）"""
    import pandas as pd

    from cpet_stage1.stats.anomaly_audit import (
        generate_anomaly_audit_report,
        run_anomaly_audit,
    )
    from cpet_stage1.stats.reference_quantiles import (
        build_reference_subset_stage1b,
        load_reference_spec,
    )

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]Stage 1B: Anomaly Audit[/bold blue]")

    staging_path = Path(staging)
    if not staging_path.exists():
        console.print(f"[red]staging 不存在: {staging_path}[/red]")
        raise typer.Exit(1)

    df = pd.read_parquet(staging_path)
    df = _derive_stage1b_columns(df)

    try:
        spec_cfg = load_reference_spec("configs/data/reference_spec_stage1b.yaml")
        df_with_flags = build_reference_subset_stage1b(df, spec_cfg)
        ref_mask = df_with_flags["reference_flag_strict"]
    except Exception:
        ref_mask = None

    result = run_anomaly_audit(df, reference_mask=ref_mask)
    console.print(result.summary())

    out_df = result.scores.reindex(df.index)
    Path(output_parquet).parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(output_parquet)
    console.print(f"[green]✓ output: {output_parquet}[/green]")

    report = generate_anomaly_audit_report(result, output_path=report_output)
    console.print(f"[green]✓ report: {report_output}[/green]")


# ─────────────────────────────────────────────────────
# Stage 1B Pipeline（全管线）
# ─────────────────────────────────────────────────────

pipeline_app = typer.Typer(help="Stage 1B 全管线命令")
app.add_typer(pipeline_app, name="pipeline")


@pipeline_app.command("stage1b")
def pipeline_stage1b(
    staging: str = typer.Option(
        "data/staging/cpet_staging_v1.parquet",
        help="staging parquet 路径",
    ),
    output_table: str = typer.Option(
        "data/output/stage1b_output_table.parquet",
        help="全量输出表路径",
    ),
    report_output: str = typer.Option(
        "reports/stage1b_summary_report.md",
        help="汇总报告路径",
    ),
    reference_spec: str = typer.Option(
        "configs/data/reference_spec_stage1b.yaml",
        help="reference_spec_stage1b.yaml 路径",
    ),
    # 各阶段中间 parquet 路径
    phenotype_parquet: str = typer.Option(
        "data/features/phenotype_burden_stage1b.parquet",
        help="phenotype parquet 路径",
    ),
    instability_parquet: str = typer.Option(
        "data/features/instability_stage1b.parquet",
        help="instability parquet 路径",
    ),
    confidence_parquet: str = typer.Option(
        "data/features/confidence_stage1b.parquet",
        help="confidence parquet 路径",
    ),
    outcome_parquet: str = typer.Option(
        "data/features/outcome_anchor_stage1b.parquet",
        help="outcome parquet 路径",
    ),
    anomaly_parquet: str = typer.Option(
        "data/features/anomaly_audit_stage1b.parquet",
        help="anomaly parquet 路径",
    ),
) -> None:
    """Stage 1B 全管线聚合报告（汇聚所有中间输出 → 最终输出表 + 摘要报告）"""
    import pandas as pd

    from cpet_stage1.reporting.stage1b_report import (
        build_stage1b_output_table,
        generate_stage1b_summary_report,
    )
    from cpet_stage1.stats.reference_quantiles import (
        build_reference_subset_stage1b,
        load_reference_spec,
    )

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    console.print("[bold blue]Stage 1B Pipeline: 全管线聚合[/bold blue]")

    staging_path = Path(staging)
    if not staging_path.exists():
        console.print(f"[red]staging 不存在: {staging_path}[/red]")
        raise typer.Exit(1)

    df = pd.read_parquet(staging_path)
    df = _derive_stage1b_columns(df)
    console.print(f"  staging: {len(df)} 行")

    # 构建输出表（合并各阶段中间结果）
    def _opt_path(p: str) -> str | None:
        return p if Path(p).exists() else None

    out_df = build_stage1b_output_table(
        df,
        phenotype_parquet=_opt_path(phenotype_parquet),
        instability_parquet=_opt_path(instability_parquet),
        confidence_parquet=_opt_path(confidence_parquet),
        outcome_parquet=_opt_path(outcome_parquet),
        anomaly_parquet=_opt_path(anomaly_parquet),
    )

    # 获取 reference mask
    ref_mask = None
    try:
        spec_cfg = load_reference_spec(reference_spec)
        df_with_flags = build_reference_subset_stage1b(df, spec_cfg)
        ref_mask = df_with_flags["reference_flag_strict"].reindex(out_df.index)
    except Exception as exc:
        console.print(f"[yellow]Warning: 无法构建 reference mask: {exc}[/yellow]")

    # 保存输出表
    Path(output_table).parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(output_table)
    console.print(f"[green]✓ 输出表: {output_table} ({len(out_df)} 行, {len(out_df.columns)} 列)[/green]")

    # 导出独立 final_zone 标签表（P8）
    zone_output = Path("data/labels/final_zone_stage1b.parquet")
    zone_output.parent.mkdir(parents=True, exist_ok=True)
    zone_cols = ["final_zone", "confidence_label", "indeterminate_flag", "phenotype_zone",
                 "instability_severe", "instability_mild"]
    out_df[[c for c in zone_cols if c in out_df.columns]].to_parquet(zone_output)
    console.print(f"[green]✓ final_zone 标签表: {zone_output}[/green]")

    # 生成报告
    report = generate_stage1b_summary_report(
        out_df,
        reference_mask=ref_mask,
        output_path=report_output,
    )
    console.print(f"[green]✓ 报告: {report_output}[/green]")

    # 在控制台显示验收判定
    if "验收判定" in report or "Accept" in report or "Warn" in report or "Fail" in report:
        for line in report.split("\n"):
            if "验收判定" in line or "verdict" in line.lower():
                console.print(f"  [bold]{line.strip()}[/bold]")
                break


if __name__ == "__main__":
    app()
