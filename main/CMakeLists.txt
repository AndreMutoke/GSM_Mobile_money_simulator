# Enregistre le composant principal et déclare ses dépendances
idf_component_register(SRCS "main.c"
                    INCLUDE_DIRS "."
                    REQUIRES esp_http_server nvs_flash esp_wifi littlefs
                    PRIV_REQUIRES esp_driver_uart)

# Commande magique pour créer et flasher automatiquement le dossier "data" dans la partition LittleFS !
littlefs_create_partition_image(storage ../data FLASH_IN_PROJECT)