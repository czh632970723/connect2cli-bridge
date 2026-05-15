from pathlib import Path

from workspace_bridge.runtime import build_bot_config, list_session_records, load_session_record, prepare_session_run, stable_session_id


def write_skill(root: Path, name: str, body: str) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")


def test_stable_session_id_is_deterministic() -> None:
    first = stable_session_id("bot-1", "single:alice")
    second = stable_session_id("bot-1", "single:alice")

    assert first == second


def test_prepare_session_run_builds_launch_spec_and_persists_session(tmp_path: Path) -> None:
    source_dir = tmp_path / "repo"
    runtime_root = tmp_path / "runtime"
    global_skill_dir = tmp_path / "global-skills"
    chatfile_root = tmp_path / "chatfiles"
    source_dir.mkdir()
    global_skill_dir.mkdir()
    (source_dir / "README.md").write_text("repo", encoding="utf-8")
    write_skill(global_skill_dir, "deploy", "# deploy")
    bot = build_bot_config(
        bot_id="bot-1",
        bot_name="codex",
        source_dir=source_dir,
        runtime_root=runtime_root,
        global_skill_dir=global_skill_dir,
        chatfile_root=chatfile_root,
    )

    launch = prepare_session_run(bot, "single:alice")

    assert launch.cwd == launch.runtime_context.project_dir
    assert launch.session.bot_id == "bot-1"
    assert launch.session.bot_name == "codex"
    assert launch.session.chat_key == "single:alice"
    assert launch.env["WECOM_BRIDGE_SESSION_ID"] == launch.session.session_id
    assert launch.env["WECOM_BRIDGE_PROJECT_DIR"] == str(launch.cwd)
    assert launch.session.workfile_dir == launch.runtime_context.workfile_dir
    assert launch.runtime_context.effective_skill_names == ("deploy",)

    stored = load_session_record(runtime_root, launch.session.session_id)
    assert stored is not None
    assert stored.workspace_id == launch.session.workspace_id
    assert stored.project_dir == launch.cwd
    assert stored.workfile_dir == launch.runtime_context.workfile_dir


def test_prepare_session_run_reuses_stable_session_id_for_same_chat(tmp_path: Path) -> None:
    source_dir = tmp_path / "repo"
    runtime_root = tmp_path / "runtime"
    global_skill_dir = tmp_path / "global-skills"
    chatfile_root = tmp_path / "chatfiles"
    source_dir.mkdir()
    global_skill_dir.mkdir()
    bot = build_bot_config(
        bot_id="bot-1",
        bot_name="codex",
        source_dir=source_dir,
        runtime_root=runtime_root,
        global_skill_dir=global_skill_dir,
        chatfile_root=chatfile_root,
    )

    first = prepare_session_run(bot, "group-user:room-1:alice")
    second = prepare_session_run(bot, "group-user:room-1:alice")

    assert first.session.session_id == second.session.session_id
    assert first.session.workspace_id == second.session.workspace_id
    assert first.cwd == second.cwd


def test_prepare_session_run_uses_workspace_skills_over_global(tmp_path: Path) -> None:
    source_dir = tmp_path / "repo"
    runtime_root = tmp_path / "runtime"
    global_skill_dir = tmp_path / "global-skills"
    chatfile_root = tmp_path / "chatfiles"
    source_dir.mkdir()
    global_skill_dir.mkdir()
    write_skill(global_skill_dir, "deploy", "# global deploy")
    bot = build_bot_config(
        bot_id="bot-1",
        bot_name="codex",
        source_dir=source_dir,
        runtime_root=runtime_root,
        global_skill_dir=global_skill_dir,
        chatfile_root=chatfile_root,
    )

    first_launch = prepare_session_run(bot, "single:alice")
    write_skill(first_launch.workspace.workspace.skill_dir, "deploy", "# workspace deploy")
    second_launch = prepare_session_run(bot, "single:alice")

    assert "deploy" in second_launch.runtime_context.effective_skill_names


def test_list_session_records_returns_latest_first_and_preserves_thread_info(tmp_path: Path) -> None:
    source_dir = tmp_path / "repo"
    runtime_root = tmp_path / "runtime"
    global_skill_dir = tmp_path / "global-skills"
    chatfile_root = tmp_path / "chatfiles"
    source_dir.mkdir()
    global_skill_dir.mkdir()
    bot = build_bot_config(
        bot_id="bot-1",
        bot_name="codex",
        source_dir=source_dir,
        runtime_root=runtime_root,
        global_skill_dir=global_skill_dir,
        chatfile_root=chatfile_root,
    )

    first = prepare_session_run(bot, "single:alice")
    second = prepare_session_run(bot, "single:bob")
    from workspace_bridge.runtime import store_session_record
    from dataclasses import replace

    store_session_record(runtime_root, replace(first.session, thread_id="thread-a", last_run_at=1000, updated_at=1000))
    store_session_record(runtime_root, replace(second.session, thread_id="thread-b", last_run_at=2000, updated_at=2000))

    records = list_session_records(runtime_root, "bot-1")

    assert [item.session_id for item in records[:2]] == [second.session.session_id, first.session.session_id]
    assert records[0].thread_id == "thread-b"
