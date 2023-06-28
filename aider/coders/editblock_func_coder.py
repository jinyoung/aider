import os

from aider import diffs

from ..dump import dump  # noqa: F401
from .base_coder import Coder
from .editblock_func_prompts import EditBlockFunctionPrompts


class EditBlockFunctionCoder(Coder):
    functions = [
        dict(
            name="replace_lines",
            description="create or update one or more files",
            parameters=dict(
                type="object",
                required=["explanation", "edits"],
                properties=dict(
                    explanation=dict(
                        type="string",
                        description=(
                            "Step by step plan for the changes to be made to the code (future"
                            " tense, markdown format)"
                        ),
                    ),
                    edits=dict(
                        type="array",
                        items=dict(
                            type="object",
                            required=["path", "original_lines", "updated_lines"],
                            properties=dict(
                                path=dict(
                                    type="string",
                                    description="Path of file to edit",
                                ),
                                original_lines=dict(
                                    type="string",
                                    description=(
                                        "Lines from the original file, including all"
                                        " whitespace, newlines, without skipping any lines"
                                    ),
                                ),
                                updated_lines=dict(
                                    type="string",
                                    description="New content to replace the `original_lines` with",
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    ]

    def __init__(self, *args, **kwargs):
        self.gpt_prompts = EditBlockFunctionPrompts()
        super().__init__(*args, **kwargs)

    def update_cur_messages(self, content, edited):
        if edited:
            self.cur_messages += [
                dict(role="assistant", content=self.gpt_prompts.redacted_edit_message)
            ]
        else:
            self.cur_messages += [dict(role="assistant", content=content)]

    def get_context_from_history(self, history):
        context = ""
        if history:
            context += "# Context:\n"
            for msg in history:
                if msg["role"] == "user":
                    context += msg["role"].upper() + ": " + msg["content"] + "\n"
        return context

    def render_incremental_response(self, final=False):
        if self.partial_response_content:
            return self.partial_response_content

        args = self.parse_partial_args()

        if not args:
            return

        explanation = args.get("explanation")
        files = args.get("files", [])

        res = ""
        if explanation:
            res += f"{explanation}\n\n"

        for i, file_upd in enumerate(files):
            path = file_upd.get("path")
            if not path:
                continue
            content = file_upd.get("content")
            if not content:
                continue

            this_final = (i < len(files) - 1) or final
            res += self.live_diffs(path, content, this_final)

        return res

    def live_diffs(self, fname, content, final):
        lines = content.splitlines(keepends=True)

        # ending an existing block
        full_path = os.path.abspath(os.path.join(self.root, fname))

        with open(full_path, "r") as f:
            orig_lines = f.readlines()

        show_diff = diffs.diff_partial_update(
            orig_lines,
            lines,
            final,
            fname=fname,
        ).splitlines()

        return "\n".join(show_diff)

    def update_files(self):
        name = self.partial_response_function_call.get("name")
        if name and name != "replace_lines":
            raise ValueError(f'Unknown function_call name="{name}", use name="write_file"')

        args = self.parse_partial_args()
        if not args:
            return

        files = args.get("files", [])

        edited = set()
        for file_upd in files:
            path = file_upd.get("path")
            if not path:
                raise ValueError(f"Missing path parameter: {file_upd}")

            content = file_upd.get("content")
            if not content:
                raise ValueError(f"Missing content parameter: {file_upd}")

            if self.allowed_to_edit(path, content):
                edited.add(path)

        return edited