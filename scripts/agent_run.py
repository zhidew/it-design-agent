import sys
import json
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

def print_banner(text):
    print(f"\n" + "="*60)
    print(f"🤖 {text}")
    print("="*60)

def run_subagent(script_path: Path, baseline_path: Path, output_dir: Path, name: str):
    print(f"[{name}] 开始执行设计任务...")
    # On Windows, use sys.executable to run python scripts reliably
    cmd = [sys.executable, str(script_path), str(baseline_path), str(output_dir)]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode == 0:
        print(f"✅ [{name}] 产物生成成功。")
        return True
    else:
        print(f"❌ [{name}] 任务失败！\n错误信息: {result.stderr}")
        return False

def main():
    if len(sys.argv) != 3:
        print("Usage: python agent_run.py <path_to_baseline.json> <output_project_dir>")
        sys.exit(1)

    baseline_path = Path(sys.argv[1]).resolve()
    output_dir = Path(sys.argv[2]).resolve()
    base_dir = Path(__file__).resolve().parent.parent

    if not baseline_path.exists():
        print(f"Error: 需求基线文件未找到 {baseline_path}")
        sys.exit(1)

    print_banner("IT 详细设计 Orchestrator 启动")
    print(f"读取需求基线: {baseline_path.name}")
    print(f"目标输出目录: {output_dir}")

    # 定义所有的子代理脚本路径
    skills_dir = base_dir / "skills"
    subagents = {
        "架构映射 (Architecture)": skills_dir / "architecture-mapping" / "scripts" / "render_architecture_mapping_stub.py",
        "API 契约 (API Design)": skills_dir / "api-design" / "scripts" / "render_contract_stub.py",
        "数据建模 (Data Design)": skills_dir / "data-design" / "scripts" / "render_data_stub.py",
        "流程状态 (Flow Design)": skills_dir / "flow-design" / "scripts" / "render_flow_design_stub.py",
        "领域设计 (DDD Structure)": skills_dir / "ddd-structure" / "scripts" / "render_ddd_structure_stub.py",
        "集成设计 (Integration)": skills_dir / "integration-design" / "scripts" / "render_integration_design_stub.py",
        "配置设计 (Config Design)": skills_dir / "config-design" / "scripts" / "render_config_design_stub.py",
        "测试设计 (Test Design)": skills_dir / "test-design" / "scripts" / "render_test_design_stub.py",
        "运行就绪 (Ops Readiness)": skills_dir / "ops-readiness" / "scripts" / "render_ops_readiness_stub.py",
    }

    print_banner("阶段 1: 并行调度 Subagents 执行垂直领域设计")
    
    # 使用线程池并发执行子代理任务，提高生成速度
    success = True
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        for name, script_path in subagents.items():
            if script_path.exists():
                futures.append(executor.submit(run_subagent, script_path, baseline_path, output_dir, name))
            else:
                print(f"⚠️ 警告: 找不到子代理脚本 {script_path}")
        
        for future in futures:
            if not future.result():
                success = False

    if not success:
        print("\n❌ 阶段 1 失败：部分子代理未能成功生成产物。")
        sys.exit(1)

    print_banner("阶段 2: 调度 Design Assembler 汇编最终文档")
    assembler_script = skills_dir / "design-assembler" / "scripts" / "render_design_assembler_stub.py"
    if not run_subagent(assembler_script, baseline_path, output_dir, "设计汇编 (Design Assembler)"):
        sys.exit(1)

    print_banner("阶段 3: 触发 CI 质量门禁校验 (Validator Engine)")
    validator_script = base_dir / "scripts" / "validate_artifacts.py"
    cmd = [sys.executable, str(validator_script), "--project", str(output_dir)]
    
    # 实时打印校验输出
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    for line in process.stdout:
        print(line, end="")
    process.wait()

    if process.returncode == 0:
        print_banner("🎉 全流程执行完毕！高质量设计包已生成并完美通过门禁校验。")
    else:
        print_banner("❌ 全流程执行结束，但未能通过质量门禁，请检查上方日志。")
        sys.exit(1)

if __name__ == "__main__":
    main()
