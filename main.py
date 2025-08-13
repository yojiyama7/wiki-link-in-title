import re
import shlex
import json
import os
import unicodedata  # 表示幅の計算に必要
from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory

def get_display_width(text: str) -> int:
    """
    文字列の表示幅を計算する。全角文字は2、半角文字は1としてカウント。
    """
    width = 0
    for char in text:
        # 'F' (Fullwidth), 'W' (Wide), 'A' (Ambiguous) を全角文字(幅2)として扱う
        if unicodedata.east_asian_width(char) in ('F', 'W', 'A'):
            width += 2
        else:
            width += 1
    return width

class Wiki:
  """
  ノート管理を行うWiki。リンクとバックリンクは都度計算する。
  データは id, title, uname のみ保持する。
  """

  def __init__(self, filepath='wiki_data_simple.json'):
    self.filepath = filepath
    self.notes = {} # {id: {"id": int, "title": str, "uname": str}}
    self.uname_to_id = {} # {uname: id}
    self._next_id = 1
    self._load_data()

  def _save_data(self):
    """現在のノートデータをJSONファイルに保存する。"""
    try:
      data_to_save = {
        '_next_id': self._next_id,
        'notes': self.notes
      }
      with open(self.filepath, 'w', encoding='utf-8') as f:
        json.dump(data_to_save, f, ensure_ascii=False, indent=2)
    except IOError as e:
      print(f"エラー: データの保存に失敗しました - {e}")

  def _load_data(self):
    """JSONファイルからノートデータを読み込む。"""
    if not os.path.exists(self.filepath):
      return
    try:
      with open(self.filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
        self._next_id = data.get('_next_id', 1)
        loaded_notes = {int(k): v for k, v in data.get('notes', {}).items()}
        self.notes = loaded_notes
        self.uname_to_id = {note['uname']: note_id for note_id, note in self.notes.items()}
    except (IOError, json.JSONDecodeError) as e:
      print(f"エラー: データの読み込みに失敗しました - {e}")

  def _is_title_valid(self, title: str) -> bool:
    """タイトルの形式を検証する。二重リンクを禁止する。"""
    links_content = re.findall(r'\[\[(.+?)\]\]', title)
    return not any('[[' in content or ']]' in content for content in links_content)

  def _parse_uname(self, title: str) -> str:
    """タイトルからunameを生成する。"""
    return re.sub(r'\[\[|\]\]', '', title)
  
  def _calculate_links(self, note_id: int) -> set[str]:
    """指定されたノートのタイトルからリンク先のunameリストを計算する。"""
    if note_id not in self.notes:
      return set()
    return set(re.findall(r'\[\[(.+?)\]\]', self.notes[note_id]['title']))

  def _calculate_backlinks(self, target_uname: str) -> list[int]:
    """指定されたunameへリンクしているノートのIDリストを計算する。"""
    backlink_ids = []
    link_pattern = f"[[{re.escape(target_uname)}]]"
    for note_id, note in self.notes.items():
      if link_pattern in note['title']:
        backlink_ids.append(note_id)
    return backlink_ids

  def ls(self) -> str:
    """ノートの一覧を、表示幅を考慮して整形して返す"""
    if not self.notes:
      return "ノートはありません。"
    
    headers = ["ID", "Unique Name (uname)", "Title"]
    
    # 各列の最大「表示幅」を計算
    col_widths = [get_display_width(h) for h in headers]
    for note in self.notes.values():
      col_widths[0] = max(col_widths[0], get_display_width(str(note['id'])))
      col_widths[1] = max(col_widths[1], get_display_width(note['uname']))
      col_widths[2] = max(col_widths[2], get_display_width(note['title']))
      
    # 各行をフォーマットする内部関数
    def format_row(items, widths):
      formatted_items = []
      for item, width in zip(items, widths):
        # 表示幅を元に、必要な半角スペースの数を計算してパディング
        padding_count = width - get_display_width(item)
        padding = " " * padding_count
        formatted_items.append(item + padding)
      return " | ".join(formatted_items)

    header_line = format_row(headers, col_widths)
    separator = "-" * len(header_line)
    
    lines = []
    for note in sorted(self.notes.values(), key=lambda x: x['id']):
      row_items = [str(note['id']), note['uname'], note['title']]
      lines.append(format_row(row_items, col_widths))
      
    return "\n".join([header_line, separator] + lines)


  def touch(self, title: str) -> str:
    """
    新しいノートを作成する。
    タイトル内のリンク先ノートが存在しない場合、それも自動で作成する。
    """
    if not self._is_title_valid(title):
      return "エラー: タイトルに二重のリンクを含めることはできません。"
    uname = self._parse_uname(title)
    if not uname: return "エラー: タイトルが空です。"
    if uname in self.uname_to_id: return f"エラー: '{uname}' という名前のノートは既に存在します。"
    
    new_id = self._next_id
    self.notes[new_id] = {"id": new_id, "title": title, "uname": uname}
    self.uname_to_id[uname] = new_id
    self._next_id += 1
    
    linked_unames = self._calculate_links(new_id)
    created_placeholders = []
    for placeholder_uname in linked_unames:
      if placeholder_uname not in self.uname_to_id:
        placeholder_id = self._next_id
        self.notes[placeholder_id] = {"id": placeholder_id, "title": placeholder_uname, "uname": placeholder_uname}
        self.uname_to_id[placeholder_uname] = placeholder_id
        self._next_id += 1
        created_placeholders.append(f"'{placeholder_uname}'")

    self._save_data()

    main_message = f"ノート {new_id} ('{uname}') を作成しました。"
    if created_placeholders:
      placeholder_message = f"リンク先の未作成ノート {', '.join(created_placeholders)} も同時に作成しました。"
      return f"{main_message}\n{placeholder_message}"
    else:
      return main_message

  def edit(self, note_id: int, new_title: str) -> str:
    """既存のノートを編集し、関連するノートを再帰的に更新する。"""
    if not self._is_title_valid(new_title): return "エラー: タイトルに二重のリンクを含めることはできません。"
    if note_id not in self.notes: return f"エラー: ID '{note_id}' のノートは存在しません。"
    
    new_uname = self._parse_uname(new_title)
    if not new_uname: return "エラー: 新しいタイトルが空です。"
    if new_uname in self.uname_to_id and self.uname_to_id[new_uname] != note_id:
      return f"エラー: '{new_uname}' という名前のノートは既に存在します。"
    
    old_uname = self.notes[note_id]["uname"]

    if old_uname in self.uname_to_id: del self.uname_to_id[old_uname]
    self.uname_to_id[new_uname] = note_id
    self.notes[note_id]["title"] = new_title
    self.notes[note_id]["uname"] = new_uname
    
    if old_uname != new_uname:
      old_link_text = f"[[{old_uname}]]"
      new_link_text = f"[[{new_uname}]]"
      self._propagate_change_recursively(note_id, old_link_text, new_link_text)
    
    self._save_data()
    return f"ノート {note_id} を更新しました。"

  def rm(self, note_id: int) -> str:
    """ノートを削除する。（ユーザー仕様により、リンクの更新は行わない）"""
    if note_id not in self.notes: return f"エラー: ID '{note_id}' のノートは存在しません。"
    
    uname_to_delete = self.notes[note_id]["uname"]
    
    del self.notes[note_id]
    if uname_to_delete in self.uname_to_id: del self.uname_to_id[uname_to_delete]

    self._save_data()
    return f"ノート {note_id} を削除しました。"

  def _propagate_change_recursively(self, edited_note_id, old_text, new_text):
    """
    Wiki全体でタイトルの置換を行い、unameの変更があれば再帰的に処理を続ける。
    """
    nodes_to_check = list(self.notes.keys())
    processed_ids = {edited_note_id, }

    while nodes_to_check:
      current_id = nodes_to_check.pop(0)
      if current_id in processed_ids: continue
      processed_ids.add(current_id)

      if current_id not in self.notes: continue

      note = self.notes[current_id]
      original_title = note['title']

      if old_text not in original_title: continue

      updated_title = original_title.replace(old_text, new_text)

      old_uname_of_linked_note = note['uname']
      new_uname_of_linked_note = self._parse_uname(updated_title)
      
      note['title'] = updated_title
      note['uname'] = new_uname_of_linked_note

      if old_uname_of_linked_note in self.uname_to_id: del self.uname_to_id[old_uname_of_linked_note]
      self.uname_to_id[new_uname_of_linked_note] = current_id
      
      if old_uname_of_linked_note != new_uname_of_linked_note:
        backlink_ids_to_recheck = self._calculate_backlinks(old_uname_of_linked_note)
        for an_id in backlink_ids_to_recheck:
          if an_id not in processed_ids:
            nodes_to_check.insert(0, an_id)

  def link(self, note_id: int) -> str:
    """指定したノートのリンク先一覧を計算して表示する"""
    if note_id not in self.notes: return f"エラー: ID '{note_id}' のノートは存在しません。"
    
    note = self.notes[note_id]
    linked_unames = self._calculate_links(note_id)
    
    if not linked_unames: return f"ノート '{note['uname']}' にはリンクがありません。"
    
    output = [f"ノート '{note['uname']}' からのリンク先:"]
    for uname in sorted(list(linked_unames)):
      if uname in self.uname_to_id:
        linked_id = self.uname_to_id[uname]
        output.append(f"  ID: {linked_id}, uname: {uname}, title: \"{self.notes[linked_id]['title']}\"")
      else:
        output.append(f"  (存在しないノート: {uname})")
    return "\n".join(output)

  def backlink(self, note_id: int) -> str:
    """指定したノートへのバックリンク一覧を計算して表示する"""
    if note_id not in self.notes: return f"エラー: ID '{note_id}' のノートは存在しません。"
    
    target_uname = self.notes[note_id]['uname']
    backlink_ids = self._calculate_backlinks(target_uname)

    if not backlink_ids: return f"ノート '{target_uname}' へのバックリンクはありません。"
    
    output = [f"ノート '{target_uname}' へのバックリンク元:"]
    for b_id in sorted(backlink_ids):
      note = self.notes[b_id]
      output.append(f"  ID: {note['id']}, uname: {note['uname']}, title: \"{note['title']}\"")
    return "\n".join(output)


def print_help():
  print("""
コマンド一覧:
  ls                                       : ノートの一覧を表示
  touch "<title>"                          : 新しいノートを作成 (空白を含む場合は引用符で囲む)
  edit <id> "<new_title>"                  : ノートを編集 (空白を含む場合は引用符で囲む)
  rm <id>                                  : ノートを削除
  link <id>                                : ノートのリンク先を表示
  backlink <id>                            : ノートへのバックリンク元を表示
  help                                     : このヘルプを表示
  exit / quit                              : プログラムを終了
""")

def main():
  """CLIのメインループ"""
  wiki = Wiki(filepath='wiki_data_simple.json')
  session = PromptSession(history=InMemoryHistory())
  print(f"CLI Wiki へようこそ！ (データは '{wiki.filepath}' に保存されます)")

  while True:
    try:
      user_input = session.prompt("> ")
      if not user_input.strip(): 
        continue
      
      parts = shlex.split(user_input)
      if not parts:
        continue
        
      command, args = parts[0].lower(), parts[1:]

      if command in ["exit", "quit"]:
        print("終了します。")
        break
      elif command == "help":
        print_help()
      elif command == "ls":
        if args:
          print("エラー: ls コマンドに引数は不要です。")
        else:
          print(wiki.ls())
      elif command == "touch":
        if len(args) != 1:
          print("使用法: touch \"<title>\"")
        else:
          print(wiki.touch(args[0]))
      elif command == "edit":
        if len(args) != 2:
          print("使用法: edit <id> \"<new_title>\"")
        else:
          try:
            note_id = int(args[0])
            print(wiki.edit(note_id, args[1]))
          except ValueError:
            print("エラー: IDは整数で指定してください。")
          except KeyError:
            print(f"エラー: ID '{args[0]}' のノートは存在しません。")
      elif command == "rm":
        if len(args) != 1:
          print("使用法: rm <id>")
        else:
          try:
            note_id = int(args[0])
            print(wiki.rm(note_id))
          except ValueError:
            print("エラー: IDは整数で指定してください。")
          except KeyError:
            print(f"エラー: ID '{args[0]}' のノートは存在しません。")
      elif command == "link":
        if len(args) != 1:
          print("使用法: link <id>")
        else:
          try:
            note_id = int(args[0])
            print(wiki.link(note_id))
          except ValueError:
            print("エラー: IDは整数で指定してください。")
          except KeyError:
            print(f"エラー: ID '{args[0]}' のノートは存在しません。")
      elif command == "backlink":
        if len(args) != 1:
          print("使用法: backlink <id>")
        else:
          try:
            note_id = int(args[0])
            print(wiki.backlink(note_id))
          except ValueError:
            print("エラー: IDは整数で指定してください。")
          except KeyError:
            print(f"エラー: ID '{args[0]}' のノートは存在しません。")
      else: 
        print(f"不明なコマンド: '{command}'")
        
    except KeyboardInterrupt: 
      print("\n終了します。")
      break
    except Exception as e: 
      print(f"予期せぬエラーが発生しました: {e}")

if __name__ == "__main__":
  main()