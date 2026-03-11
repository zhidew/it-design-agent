-- ==============================================================================
-- 项目名称: {{project_name}}
-- 版本: {{version}}
-- 描述: 数据库表结构定义脚本 (DDL)
-- 规范: 表名和字段名采用小写下划线命名法 (snake_case)。必须包含审计字段。
-- ==============================================================================

-- ---------------------------------------------------------
-- 表名: example_table
-- 描述: 示例表，用于存储核心业务实体数据
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS example_table (
    id BIGINT AUTO_INCREMENT COMMENT '主键ID',
    business_no VARCHAR(64) NOT NULL COMMENT '业务流水号，全局唯一',
    entity_name VARCHAR(128) NOT NULL COMMENT '实体名称',
    record_status TINYINT NOT NULL DEFAULT 0 COMMENT '状态: 0-初始, 1-处理中, 2-完成',

    -- 审计与辅助字段
    is_deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除标志: 0-未删除',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    created_by VARCHAR(64) DEFAULT NULL COMMENT '创建人',
    updated_by VARCHAR(64) DEFAULT NULL COMMENT '更新人',

    PRIMARY KEY (id),
    UNIQUE KEY uk_business_no (business_no),
    KEY idx_status_created (record_status, created_at)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '示例业务表';

-- ---------------------------------------------------------
-- [按需添加更多表定义]
-- ---------------------------------------------------------
