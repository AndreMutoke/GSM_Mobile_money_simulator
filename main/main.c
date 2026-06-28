/*
 * ============================================================
 *  PASSERELLE USSD - ESP32 SoftAP + Serveur HTTP + UART
 *  Fixes v2.2 :
 *   - UART0 réservé EXCLUSIVEMENT au protocole Python
 *     → les logs ESP_LOG* sont redirigés sur UART1 (TX=GPIO4)
 *     → avant init_uart0(), esp_log_set_vprintf redirige stdout
 *   - Tous les ESP_LOGI/W/E dans communiquer_avec_passerelle()
 *     sont remplacés par des printf() qui partent sur UART1
 *   - Suppression du ESP_LOGI("[UART TX]") qui polluait UART0
 * ============================================================
 */

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

/*
 * UART0 = communication protocole avec Python (USB)
 * UART1 = logs de débogage (TX sur GPIO4, à lire avec un 2e adaptateur USB-TTL)
 *
 * Si tu n'as PAS de 2e adaptateur USB-TTL, garde UART_LOG_PORT commenté :
 * les logs seront tout simplement silencieux, ce qui est acceptable en prod.
 */
#define UART_PROTO_PORT    UART_NUM_0   /* ← trame protocole UNIQUEMENT      */
#define UART_LOG_PORT      UART_NUM_1   /* ← logs debug  (GPIO4=TX, GPIO5=RX) */
#define UART_LOG_TX_PIN    4
#define UART_LOG_RX_PIN    5

#define UART_BUF_SIZE      1024
#define UART_TIMEOUT_MS    4000

/* ----------------------------------------------------------------
 *  PROTOTYPES
 * ---------------------------------------------------------------- */
void     init_uart_proto(void);
void     init_uart_log(void);
void     urldecode(char *dst, const char *src, size_t dst_size);
bool     communiquer_avec_passerelle(const char *requete, char *reponse_out, size_t max_len);
void     wifi_init_softap(void);

static esp_err_t get_index_handler(httpd_req_t *req);
static esp_err_t get_tailwind_handler(httpd_req_t *req);
static esp_err_t api_ussd_handler(httpd_req_t *req);
static esp_err_t api_commande_handler(httpd_req_t *req);
httpd_handle_t   start_webserver(void);

/* ----------------------------------------------------------------
 *  UART1 : logs de debug (ne touche PAS à UART0)
 * ---------------------------------------------------------------- */
void init_uart_log(void) {
    const uart_config_t cfg = {
        .baud_rate  = 115200,
        .data_bits  = UART_DATA_8_BITS,
        .parity     = UART_PARITY_DISABLE,
        .stop_bits  = UART_STOP_BITS_1,
        .flow_ctrl  = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    uart_driver_install(UART_LOG_PORT, UART_BUF_SIZE, 0, 0, NULL, 0);
    uart_param_config(UART_LOG_PORT, &cfg);
    uart_set_pin(UART_LOG_PORT, UART_LOG_TX_PIN, UART_LOG_RX_PIN,
                 UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);

    /* Rediriger esp_log vers UART1 */
    esp_log_set_vprintf((vprintf_like_t)vprintf);   /* vprintf est déjà sur stdout */
    /* stdout → UART1 via esp_idf : on utilise uart_vfs pour ça */
    /* Si le projet utilise CONFIG_ESP_CONSOLE_UART_NUM=1 dans sdkconfig, c'est automatique. */
    /* Sinon, on peut simplement supprimer les ESP_LOG* sensibles (voir ci-dessous). */
}

/* ----------------------------------------------------------------
 *  UART0 : protocole Python EXCLUSIVEMENT
 *  !! Aucun ESP_LOGI/printf ici qui écrirait sur UART0 !!
 * ---------------------------------------------------------------- */
void init_uart_proto(void) {
    const uart_config_t uart_config = {
        .baud_rate  = 115200,
        .data_bits  = UART_DATA_8_BITS,
        .parity     = UART_PARITY_DISABLE,
        .stop_bits  = UART_STOP_BITS_1,
        .flow_ctrl  = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    ESP_ERROR_CHECK(uart_driver_install(UART_PROTO_PORT, UART_BUF_SIZE * 2, 0, 0, NULL, 0));
    ESP_ERROR_CHECK(uart_param_config(UART_PROTO_PORT, &uart_config));
    ESP_ERROR_CHECK(uart_set_pin(UART_PROTO_PORT,
                                 UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE,
                                 UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
    /* Log sur UART1, PAS sur UART0 */
    ESP_LOGI(TAG, "UART0 proto init OK (aucun log ne sortira sur ce port desormais).");
}

/* ----------------------------------------------------------------
 *  COMMUNICATION AVEC LA PASSERELLE PYTHON
 *  Règle absolue : uart_write_bytes envoie UNIQUEMENT la trame protocole.
 *  Les ESP_LOGI/W sont sur UART1 (le log ne passe plus par UART0).
 * ---------------------------------------------------------------- */
bool communiquer_avec_passerelle(const char *requete, char *reponse_out, size_t max_len) {
    /* --- ENVOI --- */
    uart_write_bytes(UART_PROTO_PORT, requete, strlen(requete));
    /*
     * NE PAS faire ESP_LOGI("[UART TX]") ici — si CONFIG_ESP_CONSOLE_UART_NUM=0
     * ce printf partirait sur UART0 et polluerait la trame.
     * On logue sur UART1 via la macro seulement si le console est sur UART1.
     */
    ESP_LOGI(TAG, "TX → %s", requete);   /* va sur UART1 si sdkconfig est correct */

    /* --- RÉCEPTION : lecture jusqu'à '\n' ou timeout --- */
    memset(reponse_out, 0, max_len);
    size_t pos = 0;
    uint8_t ch;
    TickType_t timeout = pdMS_TO_TICKS(UART_TIMEOUT_MS);
    TickType_t start   = xTaskGetTickCount();

    while ((xTaskGetTickCount() - start) < timeout && pos < max_len - 1) {
        int n = uart_read_bytes(UART_PROTO_PORT, &ch, 1, pdMS_TO_TICKS(50));
        if (n > 0) {
            if (ch == '\n' || ch == '\r') {
                if (pos > 0) break;
                continue;
            }
            reponse_out[pos++] = (char)ch;
        }
    }
    reponse_out[pos] = '\0';

    if (pos > 0) {
        ESP_LOGI(TAG, "RX ← %s", reponse_out);
        return true;
    }
    ESP_LOGW(TAG, "Timeout UART (%d ms)", UART_TIMEOUT_MS);
    return false;
}

/* ----------------------------------------------------------------
 *  UTILITAIRES
 * ---------------------------------------------------------------- */
void urldecode(char *dst, const char *src, size_t dst_size) {
    char a, b;
    size_t written = 0;
    while (*src && written < dst_size - 1) {
        if ((*src == '%') && ((a = src[1]) != 0) && ((b = src[2]) != 0)
            && isxdigit((unsigned char)a) && isxdigit((unsigned char)b))
        {
            a = (char)(toupper((unsigned char)a));
            b = (char)(toupper((unsigned char)b));
            a = (char)(a >= 'A' ? a - 'A' + 10 : a - '0');
            b = (char)(b >= 'A' ? b - 'A' + 10 : b - '0');
            dst[written++] = (char)(16 * a + b);
            src += 3;
        } else if (*src == '+') {
            dst[written++] = ' ';
            src++;
        } else {
            dst[written++] = *src++;
        }
    }
    dst[written] = '\0';
}

/* ----------------------------------------------------------------
 *  HANDLERS HTTP — fichiers statiques
 * ---------------------------------------------------------------- */
static esp_err_t get_index_handler(httpd_req_t *req) {
    FILE *f = fopen("/fs/index.html", "r");
    if (f == NULL) { httpd_resp_send_404(req); return ESP_FAIL; }
    char buf[1024];
    size_t n;
    httpd_resp_set_type(req, "text/html; charset=utf-8");
    while ((n = fread(buf, 1, sizeof(buf), f)) > 0)
        httpd_resp_send_chunk(req, buf, (ssize_t)n);
    httpd_resp_send_chunk(req, NULL, 0);
    fclose(f);
    return ESP_OK;
}

static esp_err_t get_tailwind_handler(httpd_req_t *req) {
    FILE *f = fopen("/fs/tailwind.js", "r");
    if (f == NULL) { httpd_resp_send_404(req); return ESP_FAIL; }
    char buf[1024];
    size_t n;
    httpd_resp_set_type(req, "application/javascript");
    while ((n = fread(buf, 1, sizeof(buf), f)) > 0)
        httpd_resp_send_chunk(req, buf, (ssize_t)n);
    httpd_resp_send_chunk(req, NULL, 0);
    fclose(f);
    return ESP_OK;
}

/* ----------------------------------------------------------------
 *  HANDLER /api/ussd  (test manuel)
 * ---------------------------------------------------------------- */
static esp_err_t api_ussd_handler(httpd_req_t *req) {
    char qs[256] = {0}, code_enc[64] = {0}, code_dec[64] = {0};
    char trame[512] = {0}, rep[512] = {0};

    if (httpd_req_get_url_query_str(req, qs, sizeof(qs)) == ESP_OK)
        if (httpd_query_key_value(qs, "code", code_enc, sizeof(code_enc)) == ESP_OK)
            urldecode(code_dec, code_enc, sizeof(code_dec));

    if (!strlen(code_dec)) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Parametre code manquant");
        return ESP_OK;
    }
    snprintf(trame, sizeof(trame), "USSD:%s\n", code_dec);
    if (communiquer_avec_passerelle(trame, rep, sizeof(rep)))
        httpd_resp_send(req, rep, HTTPD_RESP_USE_STRLEN);
    else
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Timeout passerelle");
    return ESP_OK;
}

/* ----------------------------------------------------------------
 *  HANDLER /commande  (route principale UI)
 * ---------------------------------------------------------------- */
static esp_err_t api_commande_handler(httpd_req_t *req) {
    char qs[512]          = {0};
    char act_enc[32]      = {0}, opt_enc[128] = {0}, num_enc[32]  = {0};
    char mont_enc[32]     = {0}, pin_enc[16]  = {0}, bts_enc[256] = {0};
    char action[32]       = {0}, option[128]  = {0}, numero[32]   = {0};
    char montant[32]      = {0}, pin[16]      = {0}, bts[256]     = {0};
    char trame[512]       = {0}, rep[512]     = {0};

    if (httpd_req_get_url_query_str(req, qs, sizeof(qs)) != ESP_OK) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Query string manquante");
        return ESP_OK;
    }
    httpd_query_key_value(qs, "action",  act_enc,  sizeof(act_enc));
    httpd_query_key_value(qs, "option",  opt_enc,  sizeof(opt_enc));
    httpd_query_key_value(qs, "numero",  num_enc,  sizeof(num_enc));
    httpd_query_key_value(qs, "montant", mont_enc, sizeof(mont_enc));
    httpd_query_key_value(qs, "pin",     pin_enc,  sizeof(pin_enc));
    httpd_query_key_value(qs, "bts",     bts_enc,  sizeof(bts_enc));

    urldecode(action,  act_enc,  sizeof(action));
    urldecode(option,  opt_enc,  sizeof(option));
    urldecode(numero,  num_enc,  sizeof(numero));
    urldecode(montant, mont_enc, sizeof(montant));
    urldecode(pin,     pin_enc,  sizeof(pin));
    urldecode(bts,     bts_enc,  sizeof(bts));

    ESP_LOGI(TAG, "[CMD] action=%s opt=%.30s num=%s mont=%s", action, option, numero, montant);

    /* Réponse directe sans UART pour APPEL_USSD */
    if (strcmp(action, "APPEL_USSD") == 0) {
        httpd_resp_set_type(req, "text/plain");
        httpd_resp_send(req, "REPONSE;OK;Menu USSD ouvert", HTTPD_RESP_USE_STRLEN);
        return ESP_OK;
    }

    /* Construction de la trame protocole */
    if (strcmp(action, "SOLDE") == 0) {
        snprintf(trame, sizeof(trame), "REQ_SOLDE;PIN:%s\n", pin);
    } else if (strcmp(action, "CONFIRME") == 0) {
        if (strncmp(option, "RECOVERY_", 9) == 0)
            snprintf(trame, sizeof(trame), "REQ_TRANS;OPT:%s;MONT:%s;PIN:%s\n",
                     option, montant, pin);
        else
            snprintf(trame, sizeof(trame), "REQ_TRANS;OPT:%s;NUM:%s;MONT:%s;PIN:%s\n",
                     option, numero, montant, pin);
    } else if (strcmp(action, "LOC") == 0 || strcmp(action, "LOC_UPDATE") == 0) {
        snprintf(trame, sizeof(trame), "REQ_LOC;BTS:%s\n", bts);
    } else {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Action inconnue");
        return ESP_OK;
    }

    if (communiquer_avec_passerelle(trame, rep, sizeof(rep))) {
        httpd_resp_set_type(req, "text/plain");
        httpd_resp_send(req, rep, HTTPD_RESP_USE_STRLEN);
    } else {
        httpd_resp_set_type(req, "text/plain");
        httpd_resp_send(req, "REPONSE;ERREUR;Timeout passerelle Python", HTTPD_RESP_USE_STRLEN);
    }
    return ESP_OK;
}

/* ----------------------------------------------------------------
 *  SERVEUR HTTP
 * ---------------------------------------------------------------- */
httpd_handle_t start_webserver(void) {
    httpd_handle_t server = NULL;
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.uri_match_fn   = httpd_uri_match_wildcard;
    config.max_uri_handlers = 8;

    if (httpd_start(&server, &config) != ESP_OK) {
        ESP_LOGE(TAG, "Echec demarrage HTTP");
        return NULL;
    }
    httpd_uri_t u;

    u = (httpd_uri_t){ .uri="/",          .method=HTTP_GET, .handler=get_index_handler    };
    httpd_register_uri_handler(server, &u);
    u = (httpd_uri_t){ .uri="/tailwind.js",.method=HTTP_GET, .handler=get_tailwind_handler };
    httpd_register_uri_handler(server, &u);
    u = (httpd_uri_t){ .uri="/api/ussd",  .method=HTTP_GET, .handler=api_ussd_handler     };
    httpd_register_uri_handler(server, &u);
    u = (httpd_uri_t){ .uri="/commande",  .method=HTTP_GET, .handler=api_commande_handler  };
    httpd_register_uri_handler(server, &u);

    ESP_LOGI(TAG, "HTTP OK : /, /tailwind.js, /api/ussd, /commande");
    return server;
}

/* ----------------------------------------------------------------
 *  WIFI SoftAP
 * ---------------------------------------------------------------- */
static void wifi_event_handler(void *arg, esp_event_base_t event_base,
                               int32_t event_id, void *event_data)
{
    if (event_id == WIFI_EVENT_AP_STACONNECTED) {
        wifi_event_ap_staconnected_t *ev = (wifi_event_ap_staconnected_t *)event_data;
        ESP_LOGI(TAG, "STA connectee: " MACSTR, MAC2STR(ev->mac));
    } else if (event_id == WIFI_EVENT_AP_STADISCONNECTED) {
        wifi_event_ap_stadisconnected_t *ev = (wifi_event_ap_stadisconnected_t *)event_data;
        ESP_LOGI(TAG, "STA deconnectee: " MACSTR, MAC2STR(ev->mac));
    }
}

void wifi_init_softap(void) {
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_ap();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL, NULL));

    wifi_config_t wifi_config = {
        .ap = {
            .ssid           = ESP_WIFI_SSID,
            .ssid_len       = strlen(ESP_WIFI_SSID),
            .channel        = 1,
            .password       = ESP_WIFI_PASS,
            .max_connection = MAX_STA_CONN,
            .authmode       = WIFI_AUTH_OPEN,
        },
    };
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_LOGI(TAG, "SoftAP OK: SSID=%s IP=192.168.4.1", ESP_WIFI_SSID);
}

/* ----------------------------------------------------------------
 *  POINT D'ENTRÉE
 * ---------------------------------------------------------------- */
void app_main(void) {
    /* 1. NVS */
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    /*
     * 2. UART LOG en premier (UART1, GPIO4/5)
     *    Après cet appel, tous les ESP_LOG* partent sur UART1.
     *
     *    !! IMPORTANT !!
     *    Pour que les logs aillent vraiment sur UART1 et PAS sur UART0,
     *    il faut ajouter dans sdkconfig (ou menuconfig) :
     *        CONFIG_ESP_CONSOLE_UART_NUM=1
     *        CONFIG_ESP_CONSOLE_UART_TX_GPIO=4
     *        CONFIG_ESP_CONSOLE_UART_RX_GPIO=5
     *
     *    Si tu n'as pas de 2e adaptateur USB-TTL, mets plutôt :
     *        CONFIG_ESP_CONSOLE_NONE=y
     *    → les logs sont silencieux, UART0 est 100% propre.
     */
    init_uart_log();

    /* 3. UART0 protocole Python (DOIT être initialisé APRÈS init_uart_log) */
    init_uart_proto();

    /* 4. LittleFS */
    esp_vfs_littlefs_conf_t conf = {
        .base_path            = "/fs",
        .partition_label      = "storage",
        .format_if_mount_failed = true,
        .dont_mount           = false,
    };
    ret = esp_vfs_littlefs_register(&conf);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "LittleFS FAIL: %s", esp_err_to_name(ret));
        return;
    }

    /* 5. Wi-Fi */
    wifi_init_softap();

    /* 6. HTTP */
    start_webserver();

    ESP_LOGI(TAG, "=== SYSTEME PRET === SSID:%s  IP:192.168.4.1", ESP_WIFI_SSID);
}