#!/usr/bin/env python3
"""
SPL Front End - a small desktop GUI.

    python group_14_gui.py [program.txt]

Open (or type/paste) an SPL program and press Run. The program is lexed and
parsed exactly as in main.py; on success the syntax tree is shown (as a tree
view and as the raw tree.xml text) and can be saved as tree.xml. On failure
the error message is shown and the offending line is highlighted. Tick
"Also run type analysis" to run the optional type checker as well, and
"Also generate code" to run the whole compiler (scope analysis, type analysis,
code generation). Generated C++ can be saved or compiled and run from the GUI.

Only the standard library is used (tkinter ships with Python).
"""

import os
import shutil
import subprocess
import tempfile
import threading
import sys

import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

from spl_pipeline import analyze
from xmlwriter.xmlwriter import write_tree

APP_DIR = os.path.dirname(os.path.abspath(__file__))
MAX_TREE_ROWS = 6000   # the tree view gets slow beyond this; tree.xml is always complete

SAMPLE = """\
#x
#y
#result
:
num #add ( #a #b ) {
#tmp
:
:
#tmp = add ( #a #b ) ;
return ( #tmp )
}
void #show ( #n ) {
:
:
print "number:" ;
print ( #n ) ;
return
}
:
#x = 7 ;
#y = 3 ;
#result = #add ( #x #y ) ;
#show ( #result ) ;
print "result:" ;
print ( #result ) ;
"""


class App:
    def __init__(self, root: tk.Tk, path: str = None):
        self.root = root
        self.result = None
        self.run_token = 0
        self.compiler = next((c for c in ("g++", "c++", "clang++") if shutil.which(c)), None)
        root.title("SPL Front End")
        root.geometry("1150x740")
        root.minsize(820, 520)

        self._build_widgets()
        self._bind_keys()

        if path and self.load_file(path):
            self.run()
        else:
            self.set_source(SAMPLE, "sample program")
            self.run()

    # UI
    def _build_widgets(self):
        root = self.root
        style = ttk.Style()
        style.configure("Treeview", rowheight=22)
        self._bold = tkfont.nametofont("TkDefaultFont").copy()
        self._bold.configure(weight="bold")
        style.configure("Run.TButton", font=self._bold)
        self._mono = tkfont.nametofont("TkFixedFont").copy()
        self._mono.configure(size=11)

        # toolbar
        bar = ttk.Frame(root, padding=(8, 6))
        bar.pack(side="top", fill="x")
        ttk.Button(bar, text="Open SPL file...", command=self.open_file).pack(side="left")
        ttk.Button(bar, text="\u25b6  Run", style="Run.TButton",
                   command=self.run).pack(side="left", padx=(8, 0))
        self.scope_var = tk.BooleanVar(value=True)
        self.typecheck_var = tk.BooleanVar(value=True)
        self.codegen_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Scope analysis", variable=self.scope_var,
                        command=lambda: self._tick("scope")).pack(side="left", padx=(12, 0))
        ttk.Checkbutton(bar, text="Type analysis", variable=self.typecheck_var,
                        command=lambda: self._tick("type")).pack(side="left", padx=8)
        ttk.Checkbutton(bar, text="Generate code", variable=self.codegen_var,
                        command=lambda: self._tick("code")).pack(side="left", padx=(0, 12))
        self.save_btn = ttk.Button(bar, text="Save tree.xml...", command=self.save_xml,
                                   state="disabled")
        self.save_btn.pack(side="left")
        self.save_code_btn = ttk.Button(bar, text="Save C++...", command=self.save_code,
                                        state="disabled")
        self.save_code_btn.pack(side="left", padx=(6, 0))
        self.exec_btn = ttk.Button(bar, text="Compile & run", command=self.compile_and_run,
                                   state="disabled")
        self.exec_btn.pack(side="left", padx=(6, 0))
        self.source_label = tk.StringVar()
        ttk.Label(bar, textvariable=self.source_label, foreground="#555555").pack(side="right")

        # status bar (packed before the panes so it stays visible)
        self.cursor_label = tk.StringVar(value="Ln 1, Col 1")
        status = ttk.Frame(root, padding=(8, 2))
        status.pack(side="bottom", fill="x")
        ttk.Label(status, textvariable=self.cursor_label).pack(side="left")
        ttk.Label(status, text="Ctrl+O open    F5 / Ctrl+Enter run    Ctrl+S save tree.xml    F6 compile & run",
                  foreground="#777777").pack(side="right")

        outer = ttk.PanedWindow(root, orient="vertical")
        outer.pack(side="top", fill="both", expand=True, padx=8, pady=(0, 4))
        top = ttk.PanedWindow(outer, orient="horizontal")
        outer.add(top, weight=4)

        # --- source editor
        src_frame = ttk.LabelFrame(top, text="SPL source (editable)", padding=4)
        top.add(src_frame, weight=1)
        self.editor = tk.Text(src_frame, wrap="none", undo=True, font=self._mono,
                              width=48, height=20)
        ys = ttk.Scrollbar(src_frame, orient="vertical", command=self.editor.yview)
        xs = ttk.Scrollbar(src_frame, orient="horizontal", command=self.editor.xview)
        self.editor.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.editor.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        src_frame.rowconfigure(0, weight=1)
        src_frame.columnconfigure(0, weight=1)
        self.editor.tag_configure("errline", background="#ffd6d6")

        # --- output tabs
        self.tabs = ttk.Notebook(top)
        top.add(self.tabs, weight=1)

        tree_tab = ttk.Frame(self.tabs, padding=4)
        self.tabs.add(tree_tab, text="Syntax tree")
        btns = ttk.Frame(tree_tab)
        btns.pack(side="top", fill="x", pady=(0, 4))
        ttk.Button(btns, text="Expand all", command=lambda: self._set_open(True)).pack(side="left")
        ttk.Button(btns, text="Collapse all", command=lambda: self._set_open(False)).pack(side="left", padx=6)
        ttk.Label(btns, text="[n] = node id", foreground="#777777").pack(side="right")
        tv_frame = ttk.Frame(tree_tab)
        tv_frame.pack(side="top", fill="both", expand=True)
        self.tree = ttk.Treeview(tv_frame, show="tree", selectmode="browse")
        tys = ttk.Scrollbar(tv_frame, orient="vertical", command=self.tree.yview)
        txs = ttk.Scrollbar(tv_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=tys.set, xscrollcommand=txs.set)
        self.tree.column("#0", width=400, stretch=True)
        self.tree.grid(row=0, column=0, sticky="nsew")
        tys.grid(row=0, column=1, sticky="ns")
        txs.grid(row=1, column=0, sticky="ew")
        tv_frame.rowconfigure(0, weight=1)
        tv_frame.columnconfigure(0, weight=1)
        self.tree.tag_configure("root", font=self._bold)
        self.tree.tag_configure("leaf", foreground="#0b6b2c")
        self.tree.tag_configure("empty", foreground="#888888")

        xml_tab = ttk.Frame(self.tabs, padding=4)
        self.tabs.add(xml_tab, text="tree.xml")
        self.xml_text = tk.Text(xml_tab, wrap="none", font=self._mono, state="disabled",
                                width=40, height=10)
        xys = ttk.Scrollbar(xml_tab, orient="vertical", command=self.xml_text.yview)
        xxs = ttk.Scrollbar(xml_tab, orient="horizontal", command=self.xml_text.xview)
        self.xml_text.configure(yscrollcommand=xys.set, xscrollcommand=xxs.set)
        self.xml_text.grid(row=0, column=0, sticky="nsew")
        xys.grid(row=0, column=1, sticky="ns")
        xxs.grid(row=1, column=0, sticky="ew")
        xml_tab.rowconfigure(0, weight=1)
        xml_tab.columnconfigure(0, weight=1)

        sym_tab = ttk.Frame(self.tabs, padding=4)
        self.tabs.add(sym_tab, text="Symbol table")
        cols = ("orig", "kind", "level", "type", "line")
        self.sym = ttk.Treeview(sym_tab, columns=cols, selectmode="browse")
        self.sym.heading("#0", text="new name")
        for c, t, w in (("orig", "original", 90), ("kind", "kind", 50), ("level", "level", 50),
                        ("type", "type", 80), ("line", "line", 50)):
            self.sym.heading(c, text=t)
            self.sym.column(c, width=w, anchor="w")
        self.sym.column("#0", width=90)
        sys_ = ttk.Scrollbar(sym_tab, orient="vertical", command=self.sym.yview)
        self.sym.configure(yscrollcommand=sys_.set)
        self.sym.grid(row=0, column=0, sticky="nsew")
        sys_.grid(row=0, column=1, sticky="ns")
        sym_tab.rowconfigure(0, weight=1)
        sym_tab.columnconfigure(0, weight=1)

        self.code_text = self._text_tab("Generated C++")
        self.out_text = self._text_tab("Program output")

        # --- messages
        msg_frame = ttk.LabelFrame(outer, text="Result", padding=4)
        outer.add(msg_frame, weight=1)
        self.msg = tk.Text(msg_frame, wrap="word", height=7, font=self._mono, state="disabled")
        mys = ttk.Scrollbar(msg_frame, orient="vertical", command=self.msg.yview)
        self.msg.configure(yscrollcommand=mys.set)
        self.msg.grid(row=0, column=0, sticky="nsew")
        mys.grid(row=0, column=1, sticky="ns")
        msg_frame.rowconfigure(0, weight=1)
        msg_frame.columnconfigure(0, weight=1)
        self.msg.tag_configure("ok", foreground="#1a7f37", font=self._bold)
        self.msg.tag_configure("err", foreground="#b42318")
        self.msg.tag_configure("info", foreground="#444444")

    def _text_tab(self, title):
        frame = ttk.Frame(self.tabs, padding=4)
        self.tabs.add(frame, text=title)
        text = tk.Text(frame, wrap="none", font=self._mono, state="disabled", width=40, height=10)
        ys = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        xs = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        text.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return text

    def _tick(self, which):
        """Keep the stages consistent: code needs type needs scope."""
        if which == "code" and self.codegen_var.get():
            self.typecheck_var.set(True)
        if which == "type" and self.typecheck_var.get():
            self.scope_var.set(True)
        if which == "type" and not self.typecheck_var.get():
            self.codegen_var.set(False)
        if which == "scope" and not self.scope_var.get():
            self.typecheck_var.set(False)
            self.codegen_var.set(False)
        if self.codegen_var.get():
            self.typecheck_var.set(True)
        if self.typecheck_var.get():
            self.scope_var.set(True)

    def _bind_keys(self):
        def brk(fn):
            def handler(event=None):
                fn()
                return "break"   # stop Tk's built-in Text bindings (Ctrl+O inserts a newline!)
            return handler
        for widget in (self.root, self.editor):
            widget.bind("<F5>", brk(self.run))
            widget.bind("<Control-Return>", brk(self.run))
            widget.bind("<Control-o>", brk(self.open_file))
            widget.bind("<Control-s>", brk(self.save_xml))
            widget.bind("<F6>", brk(self.compile_and_run))
        # SPL only allows space/newline between tokens, so a real tab character would be a
        # lexical error; make the Tab key type spaces instead
        self.editor.bind("<Tab>", lambda e: (self.editor.insert("insert", "    "), "break")[1])
        for seq in ("<KeyRelease>", "<ButtonRelease-1>"):
            self.editor.bind(seq, lambda e: self._update_cursor())

    def _update_cursor(self):
        line, col = self.editor.index("insert").split(".")
        self.cursor_label.set(f"Ln {line}, Col {int(col) + 1}")

    # source
    def set_source(self, text: str, label: str):
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", text)
        self.editor.edit_reset()
        self.editor.mark_set("insert", "1.0")
        self.source_label.set(label)
        self.root.title(f"SPL Front End - {label}")
        self._update_cursor()
        self._clear_results()

    def load_file(self, path: str) -> bool:
        try:
            # default newline handling -> the editor only ever sees '\n'
            with open(path, encoding="ascii") as f:
                text = f.read()
        except UnicodeDecodeError as e:
            messagebox.showerror("Cannot open file",
                                 f"{os.path.basename(path)} is not a plain ASCII text file "
                                 f"(problem at byte {e.start}).")
            return False
        except OSError as e:
            messagebox.showerror("Cannot open file", f"Could not read {path}:\n{e}")
            return False
        self.set_source(text, os.path.basename(path))
        return True

    def open_file(self):
        path = filedialog.askopenfilename(
            title="Open SPL program",
            initialdir=APP_DIR,
            filetypes=[("SPL / text files", "*.txt *.spl"), ("All files", "*.*")])
        if path and self.load_file(path):
            self.run()

    # run
    def run(self):
        text = self.editor.get("1.0", "end-1c")
        if not text.strip():
            self._clear_results()
            self._show([("Nothing to run - open a file or type an SPL program first.\n", "info")])
            return
        self.result = analyze(text, typecheck=self.typecheck_var.get(),
                              scopecheck=self.scope_var.get(),
                              codegen=self.codegen_var.get())
        self._render(self.result)

    def _clear_results(self):
        self.result = None
        self.editor.tag_remove("errline", "1.0", "end")
        self.tree.delete(*self.tree.get_children())
        self._set_text(self.xml_text, "")
        self._show([])
        self.run_token += 1                    # a still-running program must not report back
        self.sym.delete(*self.sym.get_children())
        self._set_text(self.code_text, "")
        self._set_text(self.out_text, "")
        self.save_btn.configure(state="disabled")
        self.save_code_btn.configure(state="disabled")
        self.exec_btn.configure(state="disabled")

    def _render(self, res):
        self._clear_results()
        self.result = res
        parts = []

        if res.syntax_ok:
            self._fill_tree(res)
            self._set_text(self.xml_text, res.xml)
            self.save_btn.configure(state="normal")
            self.tabs.select(0)
            parts.append((f"\u2714 Syntax OK - syntax tree has {res.node_count} nodes. "
                          f"Use \"Save tree.xml...\" to export it.\n", "ok"))
            if res.scope_checked and not any(p.kind == "scope" for p in res.problems):
                parts.append(("\u2714 Scope analysis OK.\n", "ok"))
            if res.type_checked and not res.problems:
                parts.append(("\u2714 Type analysis OK "
                              f"(numbers are {res.number_type}).\n", "ok"))
            if res.code:
                parts.append(("\u2714 Code generation OK - see the \"Generated C++\" tab.\n", "ok"))
                self._set_text(self.code_text, res.code)
                self.save_code_btn.configure(state="normal")
                if self.compiler:
                    self.exec_btn.configure(state="normal")
                else:
                    parts.append(("No C++ compiler (g++) found on this computer, so "
                                  "\"Compile & run\" is unavailable; you can still save the C++.\n",
                                  "info"))
            self._fill_symtab(res)
        else:
            self.tree.insert("", "end", text="(no syntax tree - fix the error below)", tags=("empty",))

        for p in res.problems:
            parts.append((self._format_problem(p) + "\n", "err"))
        self._show(parts)
        self._highlight(res)

    @staticmethod
    def _format_problem(p) -> str:
        if p.kind == "scope":
            where = f" (line {p.line})" if p.line is not None else ""
            return f"\u2718 Scope error{where}: {p.message}"
        if p.kind == "type":
            where = f" (line {p.line})" if p.line is not None else ""
            return f"\u2718 Type error{where}: {p.message}"
        if p.kind == "internal":
            return f"\u2718 Internal error: {p.message}"
        return "\u2718 " + p.message      # lexical/syntax messages already name the position

    def _highlight(self, res):
        for p in res.problems:
            line = p.line
            if line is None and p.kind == "syntax":          # ran out of input: point at the end
                line = int(self.editor.index("end-1c").split(".")[0])
                while line > 1 and not self.editor.get(f"{line}.0", f"{line}.end").strip():
                    line -= 1
            if line is None:
                continue
            self.editor.tag_add("errline", f"{line}.0", f"{line}.end+1c")
            self.editor.see(f"{line}.0")
            if p.col is not None:
                self.editor.mark_set("insert", f"{line}.{max(p.col - 1, 0)}")
                self._update_cursor()
            break   # only the first located problem

    # tree view
    def _fill_tree(self, res):
        stack = [("", res.tree)]
        shown = 0
        while stack and shown < MAX_TREE_ROWS:
            parent_iid, node = stack.pop()
            shown += 1
            if node.is_leaf():
                label, tag = f"{node.contents}   [{node.id}]", "leaf"
            elif not node.children:
                label, tag = f"{node.contents}   \u03b5   [{node.id}]", "empty"
            else:
                label, tag = f"{node.contents}   [{node.id}]", ("root" if node.is_root() else "")
            iid = self.tree.insert(parent_iid, "end", text=label, open=True, tags=(tag,))
            for child in reversed(node.children):        # pre-order, siblings stay in order
                stack.append((iid, child))
        if stack:
            self.tree.insert("", "end", tags=("empty",), text=(
                f"... showing the first {shown} of {res.node_count} nodes; "
                f"see the tree.xml tab for the complete tree"))

    def _fill_symtab(self, res):
        if res.symtab is None:
            return
        entries = res.symtab.dump().items()
        def num(kv):
            digits = "".join(ch for ch in kv[0] if ch.isdigit())
            return int(digits) if digits else 0
        for name, e in sorted(entries, key=num):
            self.sym.insert("", "end", text=name, values=(
                e.get("orig_name") or "", e.get("kind") or "", e.get("scope_level", ""),
                e.get("type") or "", e.get("line") or ""))

    def _set_open(self, is_open: bool):
        stack = list(self.tree.get_children())
        while stack:
            iid = stack.pop()
            self.tree.item(iid, open=is_open)
            stack.extend(self.tree.get_children(iid))
        if not is_open:   # keep the root itself visible/expanded one level
            for iid in self.tree.get_children():
                self.tree.item(iid, open=True)

    # messages
    @staticmethod
    def _set_text(widget: tk.Text, text: str):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _show(self, parts):
        self.msg.configure(state="normal")
        self.msg.delete("1.0", "end")
        for text, tag in parts:
            self.msg.insert("end", text, tag)
        self.msg.configure(state="disabled")

    def _append_message(self, text: str, tag: str):
        self.msg.configure(state="normal")
        self.msg.insert("end", text, tag)
        self.msg.configure(state="disabled")
        self.msg.see("end")

    # ---------------------------------------------------------------- save
    def save_xml(self):
        if not (self.result and self.result.syntax_ok):
            return
        path = filedialog.asksaveasfilename(
            title="Save syntax tree", defaultextension=".xml", initialfile="tree.xml",
            filetypes=[("XML files", "*.xml"), ("All files", "*.*")])
        if not path:
            return
        try:
            write_tree(self.result.tree, path)
        except OSError as e:
            messagebox.showerror("Cannot save file", f"Could not write {path}:\n{e}")
            return
        self._append_message(f"Saved syntax tree to {path}\n", "info")


    def save_code(self):
        if not (self.result and self.result.code):
            return
        path = filedialog.asksaveasfilename(
            title="Save generated C++", defaultextension=".cpp", initialfile="out.cpp",
            filetypes=[("C++ files", "*.cpp"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "w", encoding="ascii", newline="\n") as f:
                f.write(self.result.code)
        except OSError as e:
            messagebox.showerror("Cannot save file", f"Could not write {path}:\n{e}")
            return
        self._append_message(f"Saved generated C++ to {path}\n", "info")

    # ------------------------------------------------------- compile & run
    def compile_and_run(self):
        if not (self.result and self.result.code and self.compiler):
            return
        self.exec_btn.configure(state="disabled")
        self._set_text(self.out_text, "Compiling and running...\n")
        self.tabs.select(self.out_text.master)
        token, code, compiler = self.run_token, self.result.code, self.compiler

        def work():
            try:
                with tempfile.TemporaryDirectory() as d:
                    src, exe = os.path.join(d, "prog.cpp"), os.path.join(d, "prog.exe")
                    with open(src, "w", encoding="ascii", newline="\n") as f:
                        f.write(code)
                    cc = subprocess.run([compiler, src, "-o", exe], capture_output=True,
                                        text=True, timeout=60)
                    if cc.returncode != 0:
                        out, tag = "C++ compile error:\n" + cc.stderr, "err"
                    else:
                        try:
                            r = subprocess.run([exe], capture_output=True, text=True, timeout=10)
                            out = r.stdout + (f"\n[exit code {r.returncode}]" if r.returncode else "")
                            if not r.stdout:
                                out = "(the program printed nothing)" + out
                        except subprocess.TimeoutExpired:
                            out, tag = "Stopped: the program ran for more than 10 seconds " \
                                       "(endless loop?).", "err"
                        else:
                            tag = "ok"
            except Exception as e:                     # never leave the button disabled
                out, tag = f"Could not run the program: {e}", "err"
            box.append((out, tag))                     # main thread picks this up

        box = []

        def poll():
            if not box:
                self.root.after(100, poll)
                return
            done(*box[0])

        def done(out, tag):
            if token != self.run_token:
                return                                 # source was re-run meanwhile
            self._set_text(self.out_text, out)
            self.exec_btn.configure(state="normal")
            self._append_message("Program finished - see the \"Program output\" tab.\n"
                                 if tag == "ok" else "Program did not run - see the "
                                 "\"Program output\" tab.\n", "info" if tag == "ok" else "err")

        threading.Thread(target=work, daemon=True).start()
        self.root.after(100, poll)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if sys.platform == "win32":           # crisp text on high-DPI Windows displays
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk()
    App(root, argv[0] if argv else None)
    root.mainloop()


if __name__ == "__main__":
    main()
