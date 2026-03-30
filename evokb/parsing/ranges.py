from bisect import bisect_right
from typing import Optional, Sequence, Tuple

from .constants import COMMENT_PREFIXES, TYPE_NODE_TYPES


class RangeNormalizer:
    def __init__(self, min_lines: int = 0):
        self.min_lines = max(0, int(min_lines))

    def build_line_offsets(self, source_bytes: bytes):
        offsets = [0]
        pos = 0
        while True:
            pos = source_bytes.find(b"\n", pos)
            if pos == -1:
                break
            offsets.append(pos + 1)
            pos += 1
        return offsets

    def normalize_unit_byte_range(
        self,
        node,
        kind: str,
        language: str,
        source_bytes: bytes,
        line_offsets: Sequence[int],
        start_byte: int,
        end_byte: int,
    ) -> Tuple[int, int]:
        if kind == "type":
            end_byte = self._normalize_type_end(
                node=node,
                language=language,
                source_bytes=source_bytes,
                line_offsets=line_offsets,
                start_byte=start_byte,
                end_byte=end_byte,
            )
        elif kind in {"function", "method"}:
            end_byte = self._normalize_callable_end(
                node=node,
                source_bytes=source_bytes,
                line_offsets=line_offsets,
                start_byte=start_byte,
                end_byte=end_byte,
            )
        elif kind in {"global", "declaration_block"}:
            if node is not None and node.type in {"preproc_def", "preproc_function_def"}:
                pass  # tree-sitter 范围已正确（含 \ 续行），不需要扩展
            else:
                end_byte = self._normalize_global_end(
                    language=language,
                    source_bytes=source_bytes,
                    line_offsets=line_offsets,
                    start_byte=start_byte,
                    end_byte=end_byte,
                )

        end_byte = min(len(source_bytes), max(start_byte, end_byte))
        return start_byte, end_byte

    def materialize_range(
        self,
        *,
        source_bytes: bytes,
        line_offsets: Sequence[int],
        start_byte: int,
        end_byte: int,
        language: str,
        kind: str,
        include_leading_comments: bool,
        semantic_count: int = 1,
    ) -> Optional[Tuple[int, int, int, int, str]]:
        if include_leading_comments:
            start_byte = self.expand_leading_comments(
                source_bytes=source_bytes,
                line_offsets=line_offsets,
                start_byte=start_byte,
                language=language,
            )

        start_byte, end_byte = self.expand_to_full_lines(
            source_bytes=source_bytes,
            line_offsets=line_offsets,
            start_byte=start_byte,
            end_byte=end_byte,
        )
        start_byte, end_byte = self.trim_empty_boundary_lines(
            source_bytes=source_bytes,
            line_offsets=line_offsets,
            start_byte=start_byte,
            end_byte=end_byte,
        )
        text = self.build_stored_text(source_bytes, start_byte, end_byte)
        if not text:
            return None
        if not self.should_store_text(text, kind=kind, semantic_count=semantic_count):
            return None

        start_line, end_line = self.byte_range_to_lines(start_byte, end_byte, line_offsets)
        return start_byte, end_byte, start_line, end_line, text

    def line_number_for_offset(self, byte_offset: int, line_offsets: Sequence[int]) -> int:
        return bisect_right(line_offsets, byte_offset)

    def byte_range_to_lines(
        self,
        start_byte: int,
        end_byte: int,
        line_offsets: Sequence[int],
    ) -> Tuple[int, int]:
        start_line = self.line_number_for_offset(start_byte, line_offsets)
        last_byte = max(start_byte, end_byte - 1)
        end_line = self.line_number_for_offset(last_byte, line_offsets)
        return start_line, end_line

    def expand_to_full_lines(
        self,
        source_bytes: bytes,
        line_offsets: Sequence[int],
        start_byte: int,
        end_byte: int,
    ) -> Tuple[int, int]:
        if not source_bytes:
            return start_byte, end_byte

        start_line_index = self.line_number_for_offset(start_byte, line_offsets) - 1
        line_start = line_offsets[max(0, start_line_index)]

        last_byte = max(start_byte, end_byte - 1)
        end_line_index = self.line_number_for_offset(last_byte, line_offsets) - 1
        if end_line_index + 1 < len(line_offsets):
            line_end = line_offsets[end_line_index + 1]
        else:
            line_end = len(source_bytes)

        return line_start, line_end

    def trim_empty_boundary_lines(
        self,
        source_bytes: bytes,
        line_offsets: Sequence[int],
        start_byte: int,
        end_byte: int,
    ) -> Tuple[int, int]:
        if start_byte >= end_byte:
            return start_byte, start_byte

        start_line_index = self.line_number_for_offset(start_byte, line_offsets) - 1
        last_byte = max(start_byte, end_byte - 1)
        end_line_index = self.line_number_for_offset(last_byte, line_offsets) - 1

        while start_line_index <= end_line_index:
            line_start, line_end = self.line_index_to_byte_range(
                start_line_index, line_offsets, source_bytes
            )
            if not self.is_blank_line(source_bytes[line_start:line_end]):
                break
            start_line_index += 1

        while end_line_index >= start_line_index:
            line_start, line_end = self.line_index_to_byte_range(
                end_line_index, line_offsets, source_bytes
            )
            if not self.is_blank_line(source_bytes[line_start:line_end]):
                break
            end_line_index -= 1

        if start_line_index > end_line_index:
            return start_byte, start_byte

        trimmed_start, _ = self.line_index_to_byte_range(
            start_line_index, line_offsets, source_bytes
        )
        _, trimmed_end = self.line_index_to_byte_range(
            end_line_index, line_offsets, source_bytes
        )
        return trimmed_start, trimmed_end

    def build_stored_text(self, source_bytes: bytes, start_byte: int, end_byte: int) -> str:
        if start_byte >= end_byte:
            return ""
        return source_bytes[start_byte:end_byte].decode("utf-8", errors="ignore").rstrip(
            " \t\r\n"
        )

    def should_store_text(
        self,
        text: str,
        kind: Optional[str] = None,
        semantic_count: int = 1,
    ) -> bool:
        if kind == "declaration_block":
            nonempty_line_count = sum(1 for line in text.splitlines() if line.strip())
            return semantic_count > 1 or nonempty_line_count > 1
        return len(text.splitlines()) > self.min_lines

    def expand_leading_comments(
        self,
        source_bytes: bytes,
        line_offsets: Sequence[int],
        start_byte: int,
        language: str,
    ) -> int:
        prefixes = COMMENT_PREFIXES.get(language)
        if not prefixes:
            return start_byte

        row = self.line_number_for_offset(start_byte, line_offsets) - 1
        include_comment = False
        blank_count = 0
        while row > 0:
            prev_row = row - 1
            line_start = line_offsets[prev_row]
            line_end = (
                line_offsets[prev_row + 1]
                if prev_row + 1 < len(line_offsets)
                else len(source_bytes)
            )
            line_text = source_bytes[line_start:line_end].decode("utf-8", errors="ignore")
            stripped = line_text.strip()

            if not stripped:
                if include_comment:
                    blank_count += 1
                    if blank_count > 2:
                        break
                    row -= 1
                    continue
                break

            if stripped.startswith(prefixes):
                include_comment = True
                blank_count = 0
                row -= 1
                continue

            break

        return line_offsets[row] if include_comment else start_byte

    def line_index_to_byte_range(
        self,
        line_index: int,
        line_offsets: Sequence[int],
        source_bytes: bytes,
    ) -> Tuple[int, int]:
        line_start = line_offsets[line_index]
        if line_index + 1 < len(line_offsets):
            line_end = line_offsets[line_index + 1]
        else:
            line_end = len(source_bytes)
        return line_start, line_end

    def is_blank_line(self, line_bytes: bytes) -> bool:
        return not line_bytes.strip()

    def _normalize_type_end(
        self,
        node,
        language: str,
        source_bytes: bytes,
        line_offsets: Sequence[int],
        start_byte: int,
        end_byte: int,
    ) -> int:
        if node.type in TYPE_NODE_TYPES.get(language, set()):
            end_byte = max(end_byte, node.end_byte)

        return self._extend_balanced_range(
            source_bytes=source_bytes,
            line_offsets=line_offsets,
            start_byte=start_byte,
            end_byte=end_byte,
            mode="type",
        )

    def _normalize_callable_end(
        self,
        node,
        source_bytes: bytes,
        line_offsets: Sequence[int],
        start_byte: int,
        end_byte: int,
    ) -> int:
        body = node.child_by_field_name("body")
        if body is None:
            for child in node.children:
                if child.is_named and child.type in {"compound_statement", "block"}:
                    body = child
                    break
        if body is not None:
            end_byte = max(end_byte, body.end_byte)
        else:
            end_byte = max(end_byte, node.end_byte)

        return self._extend_balanced_range(
            source_bytes=source_bytes,
            line_offsets=line_offsets,
            start_byte=start_byte,
            end_byte=end_byte,
            mode="callable",
        )

    def _normalize_global_end(
        self,
        language: str,
        source_bytes: bytes,
        line_offsets: Sequence[int],
        start_byte: int,
        end_byte: int,
    ) -> int:
        if language not in {"C", "Java"}:
            return end_byte

        return self._extend_balanced_range(
            source_bytes=source_bytes,
            line_offsets=line_offsets,
            start_byte=start_byte,
            end_byte=end_byte,
            mode="statement",
        )

    def _extend_balanced_range(
        self,
        source_bytes: bytes,
        line_offsets: Sequence[int],
        start_byte: int,
        end_byte: int,
        mode: str,
        max_extra_lines: int = 64,
    ) -> int:
        if start_byte >= end_byte or (end_byte >= len(source_bytes) and mode != "type"):
            return end_byte

        limit_end = self._scan_limit_end(
            end_byte=end_byte,
            line_offsets=line_offsets,
            source_bytes=source_bytes,
            max_extra_lines=max_extra_lines,
        )
        stack = []
        in_line_comment = False
        in_block_comment = False
        in_string = False
        in_char = False
        escape = False
        saw_block_open = False

        index = start_byte
        while index < limit_end:
            current = source_bytes[index]
            next_byte = source_bytes[index + 1] if index + 1 < limit_end else None

            if in_line_comment:
                if current == ord("\\") and next_byte == ord("\n"):
                    index += 2
                    continue
                if current == ord("\n"):
                    in_line_comment = False
                index += 1
                continue

            if in_block_comment:
                if current == ord("*") and next_byte == ord("/"):
                    in_block_comment = False
                    index += 2
                    continue
                index += 1
                continue

            if in_string:
                if escape:
                    escape = False
                elif current == ord("\\"):
                    escape = True
                elif current == ord('"'):
                    in_string = False
                index += 1
                continue

            if in_char:
                if escape:
                    escape = False
                elif current == ord("\\"):
                    escape = True
                elif current == ord("'"):
                    in_char = False
                index += 1
                continue

            if current == ord("/") and next_byte == ord("/"):
                in_line_comment = True
                index += 2
                continue

            if current == ord("/") and next_byte == ord("*"):
                in_block_comment = True
                index += 2
                continue

            if current == ord('"'):
                # C++11 raw string: R"delimiter(...)delimiter"
                if index > 0 and source_bytes[index - 1] == ord('R'):
                    delim_end = source_bytes.find(b'(', index + 1, min(index + 34, limit_end))
                    if delim_end != -1:
                        delimiter = source_bytes[index + 1:delim_end]
                        closing = b')' + delimiter + b'"'
                        close_pos = source_bytes.find(closing, delim_end + 1, limit_end)
                        index = (close_pos + len(closing)) if close_pos != -1 else limit_end
                        continue
                # Java text block: """..."""
                if (next_byte == ord('"')
                        and index + 2 < limit_end
                        and source_bytes[index + 2] == ord('"')):
                    close_pos = source_bytes.find(b'"""', index + 3, limit_end)
                    index = (close_pos + 3) if close_pos != -1 else limit_end
                    continue
                in_string = True
                index += 1
                continue

            if current == ord("'"):
                in_char = True
                index += 1
                continue

            if current == ord("("):
                stack.append(ord(")"))
            elif current == ord("["):
                stack.append(ord("]"))
            elif current == ord("{"):
                stack.append(ord("}"))
                saw_block_open = True
            elif current in {ord(")"), ord("]"), ord("}")}:
                if stack and stack[-1] == current:
                    stack.pop()

            if index + 1 >= end_byte and not stack:
                if mode == "statement" and current == ord(";"):
                    return index + 1
                if mode == "callable":
                    if current == ord("}") and saw_block_open:
                        return index + 1
                    if current == ord(";") and not saw_block_open:
                        return index + 1
                if mode == "type" and current == ord("}"):
                    return self._consume_trailing_semicolon(
                        source_bytes=source_bytes,
                        start_byte=index + 1,
                        limit_end=limit_end,
                    )

            index += 1

        return end_byte

    def _scan_limit_end(
        self,
        end_byte: int,
        line_offsets: Sequence[int],
        source_bytes: bytes,
        max_extra_lines: int,
    ) -> int:
        if not source_bytes:
            return 0
        if max_extra_lines <= 0:
            return min(len(source_bytes), end_byte)

        last_byte = min(len(source_bytes) - 1, max(0, end_byte - 1))
        end_line_index = self.line_number_for_offset(last_byte, line_offsets) - 1
        limit_line_index = min(end_line_index + max_extra_lines, len(line_offsets) - 1)
        if limit_line_index + 1 < len(line_offsets):
            return line_offsets[limit_line_index + 1]
        return len(source_bytes)

    def _consume_trailing_semicolon(
        self,
        source_bytes: bytes,
        start_byte: int,
        limit_end: int,
    ) -> int:
        index = self._skip_whitespace_and_comments_forward(source_bytes, start_byte, limit_end)
        if index < limit_end and source_bytes[index] == ord(";"):
            return index + 1
        return start_byte

    def _skip_whitespace_and_comments_forward(
        self,
        source_bytes: bytes,
        start_byte: int,
        limit_end: int,
    ) -> int:
        index = start_byte
        while index < limit_end:
            current = source_bytes[index]
            next_byte = source_bytes[index + 1] if index + 1 < limit_end else None

            if chr(current).isspace():
                index += 1
                continue

            if current == ord("/") and next_byte == ord("/"):
                index += 2
                while index < limit_end and source_bytes[index] != ord("\n"):
                    index += 1
                continue

            if current == ord("/") and next_byte == ord("*"):
                index += 2
                found_end = False
                while index + 1 < limit_end:
                    if source_bytes[index] == ord("*") and source_bytes[index + 1] == ord("/"):
                        index += 2
                        found_end = True
                        break
                    index += 1
                if not found_end:
                    return limit_end
                continue

            break

        return index
