"""
navisv 磁盘缓存管理器

基于 SQLite 的编译结果缓存，避免重复解析相同的 RTL 文件。
缓存 Key: 源文件内容的 MD5 hash (files + include_dirs + defines + params)

使用方式:
    # 构建时自动使用缓存 (默认开启)
    dd = DesignDriver(['design.sv'])
    dd.build()  # 第一次慢, 后续秒级

    # 显式控制缓存
    dd = DesignDriver(['design.sv'], cache=True)
    dd.build()
    dd.persist_cache()  # 保存到 ~/.cache/navisv/cache.db

    # 强制重新解析
    dd = DesignDriver(['design.sv'], cache=False)
    dd.build()  # 不读取也不写入缓存

    # 清除缓存
    CacheManager.clear_cache()
    CacheManager.clear_cache('design.sv')
"""

import os
import sqlite3
import json
import hashlib
import pickle
import tempfile
from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass, field

from navisv.config import CACHE_DIR


@dataclass
class CacheEntry:
    """缓存条目"""
    cache_key: str           # hash of source content
    source_key: str           # 源文件列表的 hash
    files: str               # 源文件列表 (JSON)
    include_dirs: str        # include 目录 (JSON)
    defines: str             # 宏定义 (JSON)
    mtime: float             # 最后修改时间
    ast_json: str           # AST JSON 文件路径
    netlist_json: str        # Netlist JSON 文件路径
    graph_data: bytes        # 序列化后的图数据 (pickle)
    created_at: float         # 缓存创建时间


class CacheManager:
    """
    SQLite 缓存管理器

    数据库结构:
        cache_entries:
            cache_key TEXT PRIMARY KEY  -- hash of everything that affects compilation
            source_key TEXT           -- hash of just source files
            files TEXT                -- JSON list of source files
            include_dirs TEXT         -- JSON list of include dirs
            defines TEXT              -- JSON dict of defines
            mtime REAL                -- max mtime of source files
            ast_json TEXT             -- path to AST JSON (in cache dir)
            netlist_json TEXT         -- path to Netlist JSON (in cache dir)
            graph_data BLOB          -- pickled DesignGraph data
            created_at REAL          -- creation timestamp
    """

    _db_path: str = os.path.join(os.path.expanduser(CACHE_DIR), 'cache.db')
    _cache_dir: str = os.path.expanduser(CACHE_DIR)

    @classmethod
    def _ensure_dirs(cls):
        os.makedirs(cls._cache_dir, exist_ok=True)
        os.makedirs(os.path.join(cls._cache_dir, 'jsons'), exist_ok=True)

    @classmethod
    def _get_db(cls) -> sqlite3.Connection:
        cls._ensure_dirs()
        conn = sqlite3.connect(cls._db_path, timeout=30)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA busy_timeout=30000')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS cache_entries (
                cache_key TEXT PRIMARY KEY,
                source_key TEXT NOT NULL,
                files TEXT NOT NULL,
                include_dirs TEXT,
                defines TEXT,
                mtime REAL,
                ast_json TEXT,
                netlist_json TEXT,
                graph_data BLOB,
                created_at REAL
            )
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_source_key ON cache_entries(source_key)
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_created_at ON cache_entries(created_at)
        ''')
        return conn

    # ── Key 生成 ───────────────────────────────────────────────────────────

    @classmethod
    def _compute_source_key(cls, files: List[str]) -> str:
        """只基于源文件内容的 hash (快速)"""
        h = hashlib.md5()
        for f in sorted(files):
            if os.path.isfile(f):
                # 用 mtime + size 做快速检查, 文件小的话用 content hash
                st = os.stat(f)
                h.update(f"{f}:{st.st_mtime}:{st.st_size}".encode())
        return h.hexdigest()

    @classmethod
    def _compute_cache_key(
        cls,
        files: List[str],
        include_dirs: List[str],
        defines: Dict[str, str],
        params: Dict[str, str],
    ) -> str:
        """基于所有影响编译内容的 hash"""
        h = hashlib.md5()
        # 源文件内容
        for f in sorted(files):
            if os.path.isfile(f):
                h.update(f.encode())
                st = os.stat(f)
                h.update(f"{st.st_mtime}:{st.st_size}".encode())
        # include 目录
        for d in sorted(include_dirs or []):
            h.update(d.encode())
        # defines
        for k, v in sorted((defines or {}).items()):
            h.update(f"{k}={v}".encode())
        # params
        for k, v in sorted((params or {}).items()):
            h.update(f"{k}={v}".encode())
        return h.hexdigest()

    # ── 缓存查找 ────────────────────────────────────────────────────────────

    @classmethod
    def get(cls, files: List[str], include_dirs: List[str],
            defines: Dict[str, str], params: Dict[str, str]) -> Optional[CacheEntry]:
        """
        查找缓存条目

        Returns:
            CacheEntry 如果缓存命中且源文件未修改
            None 如果缓存未命中或源文件已修改
        """
        cache_key = cls._compute_cache_key(files, include_dirs, defines, params)
        source_key = cls._compute_source_key(files)

        conn = cls._get_db()
        try:
            row = conn.execute(
                'SELECT * FROM cache_entries WHERE cache_key = ?',
                (cache_key,)
            ).fetchone()

            if not row:
                return None

            # 检查源文件是否修改
            current_source_key = cls._compute_source_key(files)
            if current_source_key != row[1]:  # source_key column
                # 源文件已修改, 删除旧条目
                cls._delete_entry(cache_key)
                return None

            entry = CacheEntry(
                cache_key=row[0],
                source_key=row[1],
                files=row[2],
                include_dirs=row[3],
                defines=row[4],
                mtime=row[5],
                ast_json=row[6],
                netlist_json=row[7],
                graph_data=row[8],
                created_at=row[9],
            )
            return entry
        finally:
            conn.close()

    # ── 缓存写入 ───────────────────────────────────────────────────────────

    @classmethod
    def put(cls, files: List[str], include_dirs: List[str],
            defines: Dict[str, str], params: Dict[str, str],
            ast_json: str, netlist_json: str,
            graph_data: bytes, created_at: float) -> str:
        """
        保存缓存条目
        """
        cache_key = cls._compute_cache_key(files, include_dirs, defines, params)
        source_key = cls._compute_source_key(files)

        # 找最大 mtime
        mtime = 0.0
        for f in files:
            if os.path.isfile(f):
                mtime = max(mtime, os.stat(f).st_mtime)

        conn = cls._get_db()
        try:
            conn.execute('''
                INSERT OR REPLACE INTO cache_entries
                (cache_key, source_key, files, include_dirs, defines, mtime,
                 ast_json, netlist_json, graph_data, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                cache_key, source_key,
                json.dumps(files), json.dumps(include_dirs or []),
                json.dumps(defines or {}),
                mtime, ast_json, netlist_json, graph_data, created_at
            ))
            conn.commit()
        finally:
            conn.close()

        return cache_key

    # ── 缓存删除 ───────────────────────────────────────────────────────────

    @classmethod
    def _delete_entry(cls, cache_key: str):
        conn = cls._get_db()
        try:
            conn.execute('DELETE FROM cache_entries WHERE cache_key = ?', (cache_key,))
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def clear_cache(cls, file_pattern: Optional[str] = None) -> int:
        """
        清除缓存

        Args:
            file_pattern: 如果指定, 只删除涉及该文件的缓存
        """
        conn = cls._get_db()
        try:
            if file_pattern:
                # 删除涉及该文件的条目
                like_pattern = f'%{file_pattern}%'
                conn.execute(
                    'DELETE FROM cache_entries WHERE files LIKE ?',
                    (like_pattern,)
                )
            else:
                conn.execute('DELETE FROM cache_entries')
            count = conn.total_changes
            conn.commit()
            return count
        finally:
            conn.close()

    @classmethod
    def copy_to_cache(cls, ast_json: str, netlist_json: str) -> str:
        """
        将 JSON 文件复制到持久化缓存目录

        Returns:
            缓存目录路径
        """
        import uuid, shutil
        cls._ensure_dirs()
        cache_subdir = os.path.join(cls._cache_dir, 'jsons', uuid.uuid4().hex[:8])
        os.makedirs(cache_subdir, exist_ok=True)

        dest_ast = os.path.join(cache_subdir, 'ast.json')
        dest_netlist = os.path.join(cache_subdir, 'netlist.json')

        if os.path.exists(ast_json):
            shutil.copy2(ast_json, dest_ast)
        if os.path.exists(netlist_json):
            shutil.copy2(netlist_json, dest_netlist)

        return cache_subdir

    @classmethod
    def cache_stats(cls) -> Dict[str, Any]:
        """返回缓存统计"""
        cls._ensure_dirs()
        if not os.path.exists(cls._db_path):
            return {'entries': 0, 'size_bytes': 0, 'cache_dir': cls._cache_dir}

        conn = cls._get_db()
        try:
            row = conn.execute(
                'SELECT COUNT(*), SUM(LENGTH(graph_data)) FROM cache_entries'
            ).fetchone()
            return {
                'entries': row[0] or 0,
                'size_bytes': row[1] or 0,
                'cache_dir': cls._cache_dir,
                'db_path': cls._db_path,
            }
        finally:
            conn.close()

    # ── 缓存过期清理 ───────────────────────────────────────────────────────

    @classmethod
    def sweep(cls, max_age_days: float = 7) -> int:
        """删除超过 max_age_days 的缓存条目"""
        import time
        cutoff = time.time() - max_age_days * 86400
        conn = cls._get_db()
        try:
            conn.execute('DELETE FROM cache_entries WHERE created_at < ?', (cutoff,))
            count = conn.total_changes
            conn.commit()
            return count
        finally:
            conn.close()