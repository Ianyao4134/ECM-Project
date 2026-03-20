from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

from .config import settings


def _users_path() -> str:
  return os.path.join(settings.data_dir, "users.json")


def _projects_path() -> str:
  return os.path.join(settings.data_dir, "projects.json")


def _load_json(path: str, default: Any) -> Any:
  if not os.path.isfile(path):
    return default
  with open(path, "r", encoding="utf-8") as f:
    try:
      return json.load(f)
    except Exception:
      return default


def _save_json(path: str, data: Any) -> None:
  os.makedirs(os.path.dirname(path), exist_ok=True)
  with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)


def load_users() -> list[dict[str, Any]]:
  return _load_json(_users_path(), [])


def save_users(users: list[dict[str, Any]]) -> None:
  _save_json(_users_path(), users)


def load_projects() -> list[dict[str, Any]]:
  projects = _load_json(_projects_path(), [])
  if not isinstance(projects, list):
    return []

  changed = False
  for p in projects:
    if not isinstance(p, dict):
      continue
    if "dialogues" not in p:
      # migration: old schema stored a single "state" at project level
      old_state = p.get("state")
      if isinstance(old_state, dict):
        now = int(time.time())
        d = {
          "id": str(uuid.uuid4()),
          "name": "对话 1",
          "createdAt": p.get("createdAt") or now,
          "updatedAt": p.get("updatedAt") or now,
          "state": old_state,
        }
        p["dialogues"] = [d]
      else:
        p["dialogues"] = []
      if "state" in p:
        try:
          del p["state"]
        except Exception:
          pass
      changed = True
    else:
      if not isinstance(p.get("dialogues"), list):
        p["dialogues"] = []
        changed = True

  if changed:
    save_projects(projects)
  return projects


def save_projects(projects: list[dict[str, Any]]) -> None:
  _save_json(_projects_path(), projects)


def upsert_user(username: str, password: str) -> dict[str, Any]:
  users = load_users()
  for u in users:
    if u.get("username") == username:
      # 简单校验密码（MVP：明文）
      if u.get("password") != password:
        raise ValueError("密码不正确")
      return u
  # 登录场景下：如果用户不存在则视为错误，不自动创建
  raise ValueError("用户不存在，请先注册")


def create_user(username: str, password: str) -> dict[str, Any]:
  users = load_users()
  for u in users:
    if u.get("username") == username:
      raise ValueError("用户名已存在")
  user = {"id": str(uuid.uuid4()), "username": username, "password": password}
  users.append(user)
  save_users(users)
  return user


def list_projects(user_id: str) -> list[dict[str, Any]]:
  return [p for p in load_projects() if p.get("userId") == user_id]


def save_project(
  *,
  user_id: str,
  project_id: str | None,
  name: str,
  state: dict[str, Any],
) -> dict[str, Any]:
  now = int(time.time())
  projects = load_projects()

  if project_id:
    for p in projects:
      if p.get("id") == project_id and p.get("userId") == user_id:
        p["name"] = name or p.get("name") or "未命名项目"
        p["updatedAt"] = now
        # backward compat: save into first dialogue (create if missing)
        dialogues = p.get("dialogues")
        if not isinstance(dialogues, list):
          dialogues = []
          p["dialogues"] = dialogues
        if dialogues:
          d0 = dialogues[0]
          if isinstance(d0, dict):
            d0["state"] = state
            d0["updatedAt"] = now
        else:
          dialogues.append(
            {
              "id": str(uuid.uuid4()),
              "name": "对话 1",
              "createdAt": now,
              "updatedAt": now,
              "state": state,
            }
          )
        save_projects(projects)
        return p

  pid = str(uuid.uuid4())
  proj = {
    "id": pid,
    "userId": user_id,
    "name": name or "未命名项目",
    "createdAt": now,
    "updatedAt": now,
    "dialogues": [
      {
        "id": str(uuid.uuid4()),
        "name": "对话 1",
        "createdAt": now,
        "updatedAt": now,
        "state": state,
      }
    ],
  }
  projects.append(proj)
  save_projects(projects)
  return proj


def load_project(user_id: str, project_id: str) -> dict[str, Any] | None:
  for p in load_projects():
    if p.get("id") == project_id and p.get("userId") == user_id:
      return p
  return None


def list_dialogues(user_id: str, project_id: str) -> list[dict[str, Any]]:
  p = load_project(user_id, project_id)
  if not p:
    return []
  ds = p.get("dialogues")
  if not isinstance(ds, list):
    return []
  out: list[dict[str, Any]] = []
  for d in ds:
    if not isinstance(d, dict):
      continue
    out.append(
      {
        "id": str(d.get("id") or ""),
        "name": str(d.get("name") or "未命名对话"),
        "updatedAt": d.get("updatedAt"),
      }
    )
  out = [x for x in out if x.get("id")]
  out.sort(key=lambda x: x.get("updatedAt") or 0, reverse=True)
  return out


def create_dialogue(*, user_id: str, project_id: str, name: str) -> dict[str, Any] | None:
  now = int(time.time())
  projects = load_projects()
  for p in projects:
    if p.get("id") == project_id and p.get("userId") == user_id:
      ds = p.get("dialogues")
      if not isinstance(ds, list):
        ds = []
        p["dialogues"] = ds
      did = str(uuid.uuid4())
      d = {"id": did, "name": name or "未命名对话", "createdAt": now, "updatedAt": now, "state": {}}
      ds.append(d)
      p["updatedAt"] = now
      save_projects(projects)
      return d
  return None


def load_dialogue(user_id: str, project_id: str, dialogue_id: str) -> dict[str, Any] | None:
  p = load_project(user_id, project_id)
  if not p:
    return None
  ds = p.get("dialogues")
  if not isinstance(ds, list):
    return None
  for d in ds:
    if isinstance(d, dict) and d.get("id") == dialogue_id:
      return d
  return None


def save_dialogue(
  *,
  user_id: str,
  project_id: str,
  dialogue_id: str | None,
  name: str,
  state: dict[str, Any],
) -> dict[str, Any] | None:
  now = int(time.time())
  projects = load_projects()
  for p in projects:
    if p.get("id") == project_id and p.get("userId") == user_id:
      ds = p.get("dialogues")
      if not isinstance(ds, list):
        ds = []
        p["dialogues"] = ds
      if dialogue_id:
        for d in ds:
          if isinstance(d, dict) and d.get("id") == dialogue_id:
            d["name"] = name or d.get("name") or "未命名对话"
            d["state"] = state
            d["updatedAt"] = now
            p["updatedAt"] = now
            save_projects(projects)
            return d
      # create new
      did = str(uuid.uuid4())
      d = {"id": did, "name": name or "未命名对话", "createdAt": now, "updatedAt": now, "state": state}
      ds.append(d)
      p["updatedAt"] = now
      save_projects(projects)
      return d
  return None

