-- upgrade
-- PII for a user. Lives in the gdpr schema so a GDPR delete can drop the
-- row (or the entire schema) without touching auth.users or any
-- workspace data referencing user_id. user_name is the public handle
-- (lowercase ASCII, 3-32 chars). email is unique to prevent
-- re-registration of a deleted account.

CREATE TABLE IF NOT EXISTS gdpr.user_info (
    user_id   UUID         NOT NULL,
    email     VARCHAR      NOT NULL,
    user_name VARCHAR(32)  NOT NULL,
    config    JSONB        NOT NULL DEFAULT '{}'::JSONB,
    PRIMARY KEY (user_id),
    FOREIGN KEY (user_id) REFERENCES auth.users (user_id) ON DELETE CASCADE,
    CONSTRAINT user_info_email_unique     UNIQUE (email),
    CONSTRAINT user_info_user_name_unique UNIQUE (user_name),
    CONSTRAINT user_info_user_name_check CHECK (
        user_name ~ '^[a-z0-9][a-z0-9_-]{2,31}$'
    )
);
