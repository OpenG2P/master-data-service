export function getErrorMessage(
  error: string | null | undefined,
  code: string | null | undefined,
  t: (key: string) => string
): string {
  if (!error) return t("error_unknown");

  // Check error codes first for more precise matching
  // Attribute Service Error Codes
  if (code === "G2P-ATTR-409") {
    if (error.includes("attribute_code already exists")) {
      return t("error_attribute_code_exists");
    }
    if (error.includes("value_code already exists")) {
      return t("error_value_code_exists");
    }
    if (error.includes("Cannot delete attribute") || error.includes("Cannot delete attribute value")) {
      return t("error_cannot_delete_with_dependencies");
    }
    if (error.includes("Cannot set is_hierarchical=false")) {
      return t("error_cannot_disable_hierarchical");
    }
  }
  if (code === "G2P-ATTR-404") {
    return t("error_not_found");
  }
  if (code === "G2P-ATTR-400") {
    if (error.includes("attribute value cannot be its own parent")) {
      return t("error_cannot_be_own_parent");
    }
    if (error.includes("not hierarchical")) {
      return t("error_not_hierarchical");
    }
    return t("error_validation_failed");
  }

  // Geo Service Error Codes
  if (code === "G2P-GEO-409") {
    if (error.includes("level_mnemonic already exists")) {
      return t("error_geo_level_exists");
    }
    if (error.includes("Cannot delete level") || error.includes("Cannot delete level value")) {
      return t("error_cannot_delete_with_dependencies");
    }
  }
  if (code === "G2P-GEO-404") {
    return t("error_not_found");
  }
  if (code === "G2P-GEO-400") {
    if (error.includes("cannot be its own parent")) {
      return t("error_cannot_be_own_parent");
    }
    return t("error_validation_failed");
  }

  // Fallback to pattern matching in error message
  if (error.includes("value_code already exists")) {
    return t("error_value_code_exists");
  }
  if (error.includes("attribute_code already exists")) {
    return t("error_attribute_code_exists");
  }
  if (error.includes("level_mnemonic already exists")) {
    return t("error_geo_level_exists");
  }
  if (error.includes("geo level already exists")) {
    return t("error_geo_level_exists");
  }
  if (error.includes("geo value already exists")) {
    return t("error_geo_value_exists");
  }
  if (error.includes("not found")) {
    return t("error_not_found");
  }

  // If no pattern matches, return the original error
  return error;
}
