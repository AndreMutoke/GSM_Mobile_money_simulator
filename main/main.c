#include <stdio.h>
#include <string.h>
#include <ctype.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/uart.h"
#include "esp_mac.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "esp_littlefs.h"
#include "esp_http_server.h"

static const char *TAG = "MOTOROLA_SIM";

#define ESP_WIFI_SSID      "MTK_Global_f2"
#define ESP_WIFI_PASS      ""
#define MAX_STA_CONN       4

// Configuration UART pour communiquer avec la passerelle Python (UART0 utilise le port USB)
#define UART_PORT_NUM      UART_NUM_0
#define UART_BUF_SIZE      1024

/* --- PROTOTYPES DE FONCTIONS (Évite les erreurs de déclaration implicite) --- */
void urldecode(char *dst, const char *src);
bool communiquer_avec_passerelle(const char *requete, char *reponse_out, size_t max_len);
void init_uart0(void);
void wifi_init_softap(void);
static esp_err_t get_index_handler(httpd_req_t *req);
static esp_err_t get_tailwind_handler(httpd_req_t *req);
static esp_err_t get_commande_handler(httpd_req_t *req);
static httpd_handle_t start_webserver(void);

/* --- Implémentation : Décoder les URL --- */
void urldecode(char *dst, const char *src) {
    char a, b;
    while (*src) {
        if ((*src == '%') && ((a = src[1]) && (b = src[2])) && (isxdigit((unsigned char)a) && isxdigit((unsigned char)b))) {
            if (a >= 'a') a -= 'a'-'A';
            if (a >= 'A') a -= ('A' - 10);
            else a -= '0';
            if (b >= 'a') b -= 'a'-'A';
            if (b >= 'A') b -= ('A' - 10);
            else b -= '0';
            *dst++ = 16 * a + b;
            src += 3;
        } else if (*src == '+') {
            *dst++ = ' ';
            src++;
        } else {
            *dst++ = *src++;
        }
    }
    *dst = '\0';
}

/* --- Implémentation : Communication UART avec Python --- */
bool communiquer_avec_passerelle(const char *requete, char *reponse_out, size_t max_len) {
    // 1. ESP32 en mode NETTOYAGE : On vide l'ancienne lecture
    uart_flush_input(UART_PORT_NUM);

    // 2. ESP32 en mode ÉCRITURE exclusive
    char cmd[512];
    snprintf(cmd, sizeof(cmd), "%s\n", requete);
    uart_write_bytes(UART_PORT_NUM, cmd, strlen(cmd));
    
    // 3. SYNCHRONISATION (La magie opère ici) : 
    // On bloque l'ESP32 en mode écriture jusqu'à ce que le dernier octet 
    // soit physiquement sorti du câble USB.
    uart_wait_tx_done(UART_PORT_NUM, 1000 / portTICK_PERIOD_MS);
    
    ESP_LOGI(TAG, "Envoyé vers Python: %s", requete);

    // 4. ESP32 bascule en mode LECTURE exclusive (Il attend que Python écrive)
    uint8_t data[UART_BUF_SIZE];
    int total_bytes = 0;
    int timeout_ms = 2000;
    int elapsed = 0;

    memset(reponse_out, 0, max_len);

    while (elapsed < timeout_ms) {
        int length = 0;
        ESP_ERROR_CHECK(uart_get_buffered_data_len(UART_PORT_NUM, (size_t*)&length));
        if (length > 0) {
            int read = uart_read_bytes(UART_PORT_NUM, data + total_bytes, length, 100 / portTICK_PERIOD_MS);
            total_bytes += read;
            data[total_bytes] = '\0';

            if (strchr((char*)data, '\n') != NULL || strchr((char*)data, '\r') != NULL) {
                char *pos;
                if ((pos = strchr((char*)data, '\n')) != NULL) *pos = '\0';
                if ((pos = strchr((char*)data, '\r')) != NULL) *pos = '\0';

                strncpy(reponse_out, (char*)data, max_len - 1);
                ESP_LOGI(TAG, "Reçu de Python: %s", reponse_out);
                return true;
            }
        }
        vTaskDelay(50 / portTICK_PERIOD_MS);
        elapsed += 50;
    }

    ESP_LOGE(TAG, "Pas de réponse de la passerelle Python (Timeout)");
    return false;
}

/* --- Implémentation : HTTP GET Handlers --- */

// Servir l'interface d'accueil
static esp_err_t get_index_handler(httpd_req_t *req) {
    FILE *f = fopen("/littlefs/index.html", "r");
    if (f == NULL) {
        httpd_resp_send_err(req, HTTPD_404_NOT_FOUND, "Fichier index.html manquant.");
        return ESP_FAIL;
    }

    char line[256];
    while (fgets(line, sizeof(line), f) != NULL) {
        httpd_resp_send_chunk(req, line, strlen(line));
    }
    fclose(f);
    httpd_resp_send_chunk(req, NULL, 0);
    return ESP_OK;
}

// Servir le script tailwind.js
static esp_err_t get_tailwind_handler(httpd_req_t *req) {
    FILE *f = fopen("/littlefs/tailwind.js", "r");
    if (f == NULL) {
        httpd_resp_send_err(req, HTTPD_404_NOT_FOUND, "Fichier tailwind.js manquant.");
        return ESP_FAIL;
    }

    char *buffer = malloc(4096);
    if (buffer == NULL) {
        fclose(f);
        return ESP_ERR_NO_MEM;
    }

    size_t read_bytes;
    while ((read_bytes = fread(buffer, 1, 4096, f)) > 0) {
        httpd_resp_send_chunk(req, buffer, read_bytes);
    }
    free(buffer);
    fclose(f);
    httpd_resp_send_chunk(req, NULL, 0);
    return ESP_OK;
}

// Traiter la commande USSD (CORRIGÉ POUR ÉVITER LE STACK OVERFLOW)
static esp_err_t get_commande_handler(httpd_req_t *req) {
    // Allocation sur le Tas (Heap) avec malloc pour soulager la pile
    char *query = malloc(512);
    char *requete_passerelle = malloc(512);
    char *reponse_passerelle = malloc(512);
    
    char action[32] = {0};
    char option[128] = {0};
    char numero[64] = {0};
    char montant[64] = {0};
    char pin[16] = {0};

    // Sécurité: vérifier si l'allocation a réussi
    if (query == NULL || requete_passerelle == NULL || reponse_passerelle == NULL) {
        if (query) free(query);
        if (requete_passerelle) free(requete_passerelle);
        if (reponse_passerelle) free(reponse_passerelle);
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Erreur memoire");
        return ESP_FAIL;
    }

    memset(query, 0, 512);
    memset(requete_passerelle, 0, 512);
    memset(reponse_passerelle, 0, 512);

    if (httpd_req_get_url_query_str(req, query, 512) == ESP_OK) {
        char val[128];
        if (httpd_query_key_value(query, "action", val, sizeof(val)) == ESP_OK) {
            urldecode(action, val);
        }
        if (httpd_query_key_value(query, "option", val, sizeof(val)) == ESP_OK) {
            urldecode(option, val);
        }
        if (httpd_query_key_value(query, "numero", val, sizeof(val)) == ESP_OK) {
            urldecode(numero, val);
        }
        if (httpd_query_key_value(query, "montant", val, sizeof(val)) == ESP_OK) {
            urldecode(montant, val);
        }
        if (httpd_query_key_value(query, "pin", val, sizeof(val)) == ESP_OK) {
            urldecode(pin, val);
        }
    }

    // Choix du format de message série selon l'action
    if (strcmp(action, "SOLDE") == 0) {
        snprintf(requete_passerelle, 512, "REQ_SOLDE;PIN:%s", pin);
    } else if (strcmp(action, "CONFIRME") == 0) {
        snprintf(requete_passerelle, 512, "REQ_TRANS;OPT:%s;NUM:%s;MONT:%s;PIN:%s", option, numero, montant, pin);
    } else {
        printf("\n==========================================================\n");
        printf("                TRANSACTION USSD MTK Global                  \n");
        printf("==========================================================\n");
        printf("Action Clavier : %s\n", action);
        printf("Option Menu    : %s\n", option);
        printf("Num. Recole    : %s\n", numero);
        printf("Montant        : %s\n", montant);
        printf("==========================================================\n");
        
        httpd_resp_sendstr(req, "REP_INFO;OK;Touche enregistree localement");
        
        // Libération de la mémoire avant de quitter
        free(query); free(requete_passerelle); free(reponse_passerelle);
        return ESP_OK;
    }

    // Communiquer et attendre la réponse de la passerelle Python
    if (communiquer_avec_passerelle(requete_passerelle, reponse_passerelle, 512)) {
        httpd_resp_sendstr(req, reponse_passerelle);
    } else {
        httpd_resp_sendstr(req, "REPONSE;ERREUR;La passerelle Python ne repond pas");
    }

    // Libération de la mémoire
    free(query);
    free(requete_passerelle);
    free(reponse_passerelle);

    return ESP_OK;
}

/* --- Configuration Serveur HTTP --- */
static const httpd_uri_t index_uri = {
    .uri       = "/",
    .method    = HTTP_GET,
    .handler   = get_index_handler,
    .user_ctx  = NULL
};

static const httpd_uri_t tailwind_uri = {
    .uri       = "/tailwind.js",
    .method    = HTTP_GET,
    .handler   = get_tailwind_handler,
    .user_ctx  = NULL
};

static const httpd_uri_t commande_uri = {
    .uri       = "/commande",
    .method    = HTTP_GET,
    .handler   = get_commande_handler,
    .user_ctx  = NULL
};

static httpd_handle_t start_webserver(void) {
    httpd_handle_t server = NULL;
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.lru_purge_enable = true;

    ESP_LOGI(TAG, "Demarrage du serveur HTTP sur le port: '%d'", config.server_port);
    if (httpd_start(&server, &config) == ESP_OK) {
        httpd_register_uri_handler(server, &index_uri);
        httpd_register_uri_handler(server, &tailwind_uri);
        httpd_register_uri_handler(server, &commande_uri);
        return server;
    }

    ESP_LOGE(TAG, "Echec du demarrage du serveur HTTP.");
    return NULL;
}

/* --- Configuration Wi-Fi SoftAP --- */
static void wifi_event_handler(void* arg, esp_event_base_t event_base, int32_t event_id, void* event_data) {
    if (event_id == WIFI_EVENT_AP_STACONNECTED) {
        wifi_event_ap_staconnected_t* event = (wifi_event_ap_staconnected_t*) event_data;
        ESP_LOGI(TAG, "Station associee: "MACSTR" aid:%d", MAC2STR(event->mac), event->aid);
    } else if (event_id == WIFI_EVENT_AP_STADISCONNECTED) {
        wifi_event_ap_stadisconnected_t* event = (wifi_event_ap_stadisconnected_t*) event_data;
        ESP_LOGI(TAG, "Station deconnectee: "MACSTR" aid:%d", MAC2STR(event->mac), event->aid);
    }
}

void wifi_init_softap(void) {
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_ap();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT,
                                                        ESP_EVENT_ANY_ID,
                                                        &wifi_event_handler,
                                                        NULL,
                                                        NULL));

    wifi_config_t wifi_config = {
        .ap = {
            .ssid = ESP_WIFI_SSID,
            .ssid_len = strlen(ESP_WIFI_SSID),
            .channel = 1,
            .password = ESP_WIFI_PASS,
            .max_connection = MAX_STA_CONN,
            .authmode = WIFI_AUTH_OPEN
        },
    };

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    ESP_LOGI(TAG, "Wi-Fi AP demarre avec succes ! SSID: %s", ESP_WIFI_SSID);
}

/* --- Configuration UART0 --- */
void init_uart0(void) {
    uart_config_t uart_config = {
        .baud_rate = 115200,
        .data_bits = UART_DATA_8_BITS,
        .parity    = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };

    ESP_ERROR_CHECK(uart_driver_install(UART_PORT_NUM, UART_BUF_SIZE * 2, 0, 0, NULL, 0));
    ESP_ERROR_CHECK(uart_param_config(UART_PORT_NUM, &uart_config));
    ESP_ERROR_CHECK(uart_set_pin(UART_PORT_NUM, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
}

/* --- Main Application --- */
void app_main(void) {
    // 1. Initialiser NVS
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    // 2. Initialiser l'UART0
    init_uart0();

    // 3. Initialiser LittleFS
    ESP_LOGI(TAG, "Initialisation de LittleFS...");
    esp_vfs_littlefs_conf_t conf = {
        .base_path = "/littlefs",
        .partition_label = "storage",
        .format_if_mount_failed = true,
        .dont_mount = false,
    };

    ret = esp_vfs_littlefs_register(&conf);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Echec du montage de LittleFS (%s). Demarrage du point d'acces seul.", esp_err_to_name(ret));
    } else {
        ESP_LOGI(TAG, "Montage de LittleFS effectue avec succes !");
    }

    // 4. Initialiser le point d'acces Wi-Fi
    wifi_init_softap();

    // 5. Demarrer le serveur HTTP
    start_webserver();
}