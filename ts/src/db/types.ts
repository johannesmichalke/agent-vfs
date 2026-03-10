export interface NodeRow {
  id: string;
  user_id: string;
  path: string;
  parent_path: string;
  name: string;
  is_dir: boolean;
  content: string | null;
  summary: string | null;
  version: number;
  size: number;
  created_at: string;
  updated_at: string;
}

export interface Database {
  initialize(): Promise<void>;
  getNode(userId: string, path: string): Promise<NodeRow | undefined>;
  listChildren(userId: string, parentPath: string): Promise<NodeRow[]>;
  listDescendants(userId: string, pathPrefix: string): Promise<NodeRow[]>;
  upsertNode(node: Omit<NodeRow, "created_at" | "updated_at">): Promise<void>;
  updateContent(
    userId: string,
    path: string,
    content: string,
    size: number,
    version: number
  ): Promise<void>;
  updateSummary(userId: string, path: string, summary: string | null): Promise<void>;
  deleteNode(userId: string, path: string): Promise<void>;
  deleteTree(userId: string, pathPrefix: string): Promise<void>;
  moveNode(
    userId: string,
    oldPath: string,
    newPath: string,
    newParent: string,
    newName: string
  ): Promise<void>;
  moveTree(userId: string, oldPrefix: string, newPrefix: string): Promise<void>;
  searchContent(
    userId: string,
    likePattern: string,
    pathPrefix?: string
  ): Promise<NodeRow[]>;
  searchNames(
    userId: string,
    likePattern: string,
    pathPrefix?: string
  ): Promise<NodeRow[]>;

  // Tags
  addTag(userId: string, path: string, tag: string): Promise<void>;
  removeTag(userId: string, path: string, tag: string): Promise<void>;
  getTagsForPath(userId: string, path: string): Promise<string[]>;
  findByTag(userId: string, tag: string, pathPrefix?: string): Promise<NodeRow[]>;

  // Recent
  listRecent(userId: string, limit?: number, pathPrefix?: string): Promise<NodeRow[]>;

  close(): Promise<void>;
}
