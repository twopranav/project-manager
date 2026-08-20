markdown_content = """# Entity-Relationship (ER) Diagram

This document contains the markdown representation of the provided ER diagram. It is formatted using Mermaid.js for easy visualization and standard markdown tables for schematic details.

## 1. Mermaid ER Diagram

```mermaid
erDiagram
    USER {
        uuid id PK
        string name
        string email UK
        string password_hash
        string global_role
        timestamp created_at
    }

    PROJECT {
        uuid id PK
        string name
        text description
        uuid owner_id FK
        string status
        timestamp created_at
    }

    PROJECT_MEMBER {
        uuid id PK
        uuid project_id FK
        uuid user_id FK
        string project_role
        timestamp joined_at
    }

    TASK {
        uuid id PK
        uuid project_id FK
        uuid created_by FK
        string title
        text description
        string status
        string priority
        date due_date
        timestamp created_at
        timestamp updated_at
    }

    TASK_ASSIGNEE {
        uuid id PK
        uuid task_id FK
        uuid user_id FK
        timestamp assigned_at
    }

    COMMENT {
        uuid id PK
        uuid task_id FK
        uuid user_id FK
        uuid parent_comment_id FK
        text content
        timestamp created_at
        timestamp updated_at
    }

    TASK_STATUS_HISTORY {
        uuid id PK
        uuid task_id FK
        uuid changed_by FK
        string old_status
        string new_status
        timestamp changed_at
    }

    %% Relationships
    USER ||--o{ PROJECT : "owns"
    USER ||--o{ PROJECT_MEMBER : "is member via"
    PROJECT ||--o{ PROJECT_MEMBER : "has members via"
    PROJECT ||--o{ TASK : "contains"
    USER ||--o{ TASK : "creates"
    TASK ||--o{ TASK_ASSIGNEE : "assigned via"
    USER ||--o{ TASK_ASSIGNEE : "assigned to via"
    TASK ||--o{ COMMENT : "has"
    USER ||--o{ COMMENT : "writes"
    COMMENT ||--o{ COMMENT : "replies to"
    TASK ||--o{ TASK_STATUS_HISTORY : "tracks"
    USER ||--o{ TASK_STATUS_HISTORY : "changes"