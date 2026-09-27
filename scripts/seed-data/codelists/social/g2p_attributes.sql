-- Lists not defined by country packs (ETH core/social JSON has PROGRAM_NAME).
INSERT INTO "public"."g2p_attributes" ("attribute_id","attribute_code","attribute_display","is_hierarchical") VALUES
('PRIMARY_LIVELIHOOD','PRIMARY_LIVELIHOOD','Primary Livelihood','FALSE'),
('COPING_STRATEGY','COPING_STRATEGY','Coping Strategy','FALSE'),
('DATA_SOURCE','DATA_SOURCE','Data Source','FALSE'),
('PREFIX','PREFIX','Prefix','FALSE'),
('RELATIONSHIP_TO_THE_HEAD','RELATIONSHIP_TO_THE_HEAD','Relationship To The Head','FALSE')
ON CONFLICT (attribute_id) DO NOTHING;
