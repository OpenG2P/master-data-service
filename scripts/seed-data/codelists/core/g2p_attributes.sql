-- Default values for this registry's code lists.
--
-- Generated from the option arrays that used to live inside the widgets. They
-- are DEFAULTS, not a definition: load_attributes_from_mds replaces any list the
-- country pack also defines, and an admin can edit them in the staff portal.
-- Before this the same values were compiled into g2p_register_sections, where
-- neither route could reach them.
--
-- Values are unchanged from what the widgets carried, so a deployment with no
-- country pack behaves exactly as it did.

INSERT INTO "public"."g2p_attributes" ("attribute_id","attribute_code","attribute_display","is_hierarchical") VALUES 
('AGE_METHOD','AGE_METHOD','Age Method','FALSE'),
('CITIZENSHIP_CATEGORY','CITIZENSHIP_CATEGORY','Citizenship Category','FALSE'),
('COOKING_FUEL_TYPE','COOKING_FUEL_TYPE','Cooking Fuel Type','FALSE'),
('DISABILITY_STATUS','DISABILITY_STATUS','Disability Status','FALSE'),
('DISPLACEMENT_STATUS','DISPLACEMENT_STATUS','Displacement Status','FALSE'),
('DWELLING_TYPE','DWELLING_TYPE','Dwelling Type','FALSE'),
('EMPLOYMENT_STATUS','EMPLOYMENT_STATUS','Employment Status','FALSE'),
('FLOOR_MATERIAL','FLOOR_MATERIAL','Floor Material','FALSE'),
('GENDER','GENDER','Gender','FALSE'),
('HEADSHIP_TYPE','HEADSHIP_TYPE','Headship Type','FALSE'),
('LIGHTING_SOURCE','LIGHTING_SOURCE','Lighting Source','FALSE'),
('LIVELIHOOD','LIVELIHOOD','Livelihood','FALSE'),
('MARITAL_STATUS','MARITAL_STATUS','Marital Status','FALSE'),
('MOBILE_PHONE_TYPE','MOBILE_PHONE_TYPE','Mobile Phone Type','FALSE'),
('PASTORALIST_CLASSIFICATION','PASTORALIST_CLASSIFICATION','Pastoralist Classification','FALSE'),
('PREFERRED_CONTACT_METHOD','PREFERRED_CONTACT_METHOD','Preferred Contact Method','FALSE'),
('PRODUCTIVE_ASSET','PRODUCTIVE_ASSET','Productive Asset','FALSE'),
('RELATIONSHIP_TO_HEAD','RELATIONSHIP_TO_HEAD','Relationship To Head','FALSE'),
('RESIDENCY_STATUS','RESIDENCY_STATUS','Residency Status','FALSE'),
('ROOF_MATERIAL','ROOF_MATERIAL','Roof Material','FALSE'),
('SANITATION_TYPE','SANITATION_TYPE','Sanitation Type','FALSE'),
('TENURE_STATUS','TENURE_STATUS','Tenure Status','FALSE'),
('WALL_MATERIAL','WALL_MATERIAL','Wall Material','FALSE'),
('WATER_SOURCE_TYPE','WATER_SOURCE_TYPE','Water Source Type','FALSE')
ON CONFLICT (attribute_id) DO NOTHING;
