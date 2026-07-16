from __future__ import annotations

import argparse
import gzip
import json
import os
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from gpic_concepts_v1.atomic_io import atomic_text_writer


DEFAULT_REPO_ID = "stanford-vision-lab/gpic"
DEFAULT_REVISION = "main"


def parse_shards(values: list[str]) -> list[int]:
    shards: set[int] = set()
    for value in values:
        for part in value.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                start_s, end_s = part.split("-", 1)
                start = int(start_s)
                end = int(end_s)
                if end < start:
                    raise ValueError(f"invalid descending shard range: {part}")
                shards.update(range(start, end + 1))
            else:
                shards.add(int(part))
    return sorted(shards)


def read_hf_token() -> str | None:
    for name in ("HF_TOKEN", "HUGGINGFACE_HUB_TOKEN"):
        token = os.environ.get(name)
        if token:
            return token.strip()
    for path in (
        Path.home() / ".cache" / "huggingface" / "token",
        Path.home() / ".huggingface" / "token",
    ):
        if path.exists():
            token = path.read_text(encoding="utf-8").strip()
            if token:
                return token
    return None


def make_hf_url(repo_id: str, revision: str, split: str, shard_index: int) -> str:
    filename = f"gpic_{split}_{shard_index:05d}.tar"
    return (
        f"https://huggingface.co/datasets/{repo_id}/resolve/"
        f"{revision}/{split}/{filename}"
    )


def open_hf_tar_stream(url: str, token: str | None, timeout: int):
    headers = {"User-Agent": "gpic-caption-shard-extractor/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(
            f"HTTP {exc.code} while opening {url}. "
            "For the gated GPIC dataset, make sure the Hugging Face account "
            "has accepted the dataset conditions and HF_TOKEN is set. "
            f"Response: {message}"
        ) from exc


def write_progress(path: Path | None, payload: dict[str, object]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with atomic_text_writer(path) as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        handle.write("\n")


def extract_caption_shard(
    *,
    repo_id: str,
    revision: str,
    split: str,
    shard_index: int,
    output_dir: Path,
    token: str | None,
    timeout: int,
    overwrite: bool,
    progress_json: Path | None,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"gpic_{split}_{shard_index:05d}.jsonl.gz"
    if output_path.exists() and not overwrite:
        return {
            "shard_index": shard_index,
            "output": str(output_path),
            "status": "skipped_exists",
            "records": None,
            "seconds": 0.0,
        }

    url = make_hf_url(repo_id, revision, split, shard_index)
    temp_output = output_path.with_name(
        f".{output_path.name}.{os.getpid()}.{time.time_ns()}.tmp"
    )
    started = time.perf_counter()
    records = 0
    json_members = 0
    total_members = 0

    status_base = {
        "repo_id": repo_id,
        "revision": revision,
        "split": split,
        "shard_index": shard_index,
        "output": str(output_path),
        "url": url,
    }
    write_progress(
        progress_json,
        {
            **status_base,
            "status": "opening_remote_tar",
            "records": records,
            "seconds": round(time.perf_counter() - started, 3),
        },
    )

    try:
        response = open_hf_tar_stream(url, token, timeout)
        with response:
            with tarfile.open(fileobj=response, mode="r|") as tar_handle:
                with gzip.open(
                    temp_output, "wt", encoding="utf-8", newline=""
                ) as out_handle:
                    for member in tar_handle:
                        total_members += 1
                        if not member.isfile() or not member.name.endswith(".json"):
                            continue
                        extracted = tar_handle.extractfile(member)
                        if extracted is None:
                            continue
                        with extracted:
                            row = json.loads(
                                extracted.read().decode("utf-8", errors="replace")
                            )
                        row["_gpic_split_dir"] = split
                        row["_gpic_shard_index"] = shard_index
                        row["_gpic_shard_member"] = member.name
                        row["_gpic_record_index"] = records
                        out_handle.write(
                            json.dumps(
                                row,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            )
                        )
                        out_handle.write("\n")
                        records += 1
                        json_members += 1
                        if records == 1 or records % 1000 == 0:
                            write_progress(
                                progress_json,
                                {
                                    **status_base,
                                    "status": "extracting_json_members",
                                    "records": records,
                                    "json_members": json_members,
                                    "total_members_seen": total_members,
                                    "seconds": round(
                                        time.perf_counter() - started, 3
                                    ),
                                },
                            )
        if records == 0:
            raise RuntimeError(f"no JSON members extracted from shard {shard_index:05d}")
        os.replace(temp_output, output_path)
    except Exception:
        temp_output.unlink(missing_ok=True)
        write_progress(
            progress_json,
            {
                **status_base,
                "status": "failed",
                "records": records,
                "json_members": json_members,
                "total_members_seen": total_members,
                "seconds": round(time.perf_counter() - started, 3),
            },
        )
        raise

    result = {
        **status_base,
        "status": "downloaded_extracted",
        "records": records,
        "json_members": json_members,
        "total_members_seen": total_members,
        "seconds": round(time.perf_counter() - started, 3),
    }
    write_progress(progress_json, result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download GPIC tar shards from Hugging Face and stream only JSON "
            "caption metadata into the local gpic_*.jsonl.gz shard format."
        )
    )
    parser.add_argument("--repo-id", default=DEFAULT_REPO_ID)
    parser.add_argument("--revision", default=DEFAULT_REVISION)
    parser.add_argument("--split", default="train")
    parser.add_argument("--shards", nargs="+", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--progress-json", type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    token = read_hf_token()
    shards = parse_shards(args.shards)
    started = time.perf_counter()
    results: list[dict[str, object]] = []
    for ordinal, shard_index in enumerate(shards, start=1):
        write_progress(
            args.progress_json,
            {
                "artifact_type": "gpic_caption_shard_download_batch_progress",
                "repo_id": args.repo_id,
                "revision": args.revision,
                "split": args.split,
                "status": "running",
                "current_shard_index": shard_index,
                "current_shard_ordinal": ordinal,
                "total_shards": len(shards),
                "completed_shards": len(results),
                "records": sum(
                    int(item["records"] or 0)
                    for item in results
                    if item["status"] != "skipped_exists"
                ),
                "seconds": round(time.perf_counter() - started, 3),
            },
        )
        progress_json = None
        if args.progress_json is not None:
            progress_json = args.progress_json.with_name(
                f"{args.progress_json.stem}_{shard_index:05d}"
                f"{args.progress_json.suffix}"
            )
        result = extract_caption_shard(
            repo_id=args.repo_id,
            revision=args.revision,
            split=args.split,
            shard_index=shard_index,
            output_dir=args.output_dir,
            token=token,
            timeout=args.timeout_seconds,
            overwrite=args.overwrite,
            progress_json=progress_json,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        results.append(result)
        write_progress(
            args.progress_json,
            {
                "artifact_type": "gpic_caption_shard_download_batch_progress",
                "repo_id": args.repo_id,
                "revision": args.revision,
                "split": args.split,
                "status": "running",
                "last_result": result,
                "current_shard_index": shard_index,
                "current_shard_ordinal": ordinal,
                "total_shards": len(shards),
                "completed_shards": len(results),
                "records": sum(
                    int(item["records"] or 0)
                    for item in results
                    if item["status"] != "skipped_exists"
                ),
                "seconds": round(time.perf_counter() - started, 3),
            },
        )

    summary = {
        "artifact_type": "gpic_caption_shard_download_summary",
        "repo_id": args.repo_id,
        "revision": args.revision,
        "split": args.split,
        "output_dir": str(args.output_dir),
        "shards": shards,
        "results": results,
        "records": sum(
            int(item["records"] or 0)
            for item in results
            if item["status"] != "skipped_exists"
        ),
        "seconds": round(time.perf_counter() - started, 3),
        "token_present": bool(token),
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    with atomic_text_writer(args.summary) as handle:
        handle.write(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        handle.write("\n")
    write_progress(args.progress_json, {**summary, "status": "complete"})


if __name__ == "__main__":
    main()
