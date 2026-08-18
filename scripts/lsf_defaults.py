"""Shared LSF defaults for umbrella and related GPU jobs."""

from __future__ import annotations


DEFAULT_EXCLUDED_HOSTS = ("gpu31",)


def resolved_exclude_hosts(hosts: list[str] | None) -> list[str]:
    if hosts is None:
        return list(DEFAULT_EXCLUDED_HOSTS)
    return list(hosts)
