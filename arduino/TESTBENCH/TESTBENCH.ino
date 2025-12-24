// NOMBRE: Ruben Sahuquillo Redondo
// ASIGNATURA: Sistemas embebidos
// DESCRIPCION: Firmware Banco de Pruebas de Motores


// --- LIBRERIAS --- //
#include <HX711.h>
#include <WiFi.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>

// --- ESTADOS --- //
#define STOP 0
#define TESTING 1
#define TARE 2
#define CALIB 3

// --- PINES --- //
#define SCK2 17
#define DT2 16
#define SCK1 27
#define DT1 14
#define TACOMETRO 25
#define SENSOR_CORRIENTE 34
#define MOTOR_PIN 26

// --- VARIABLES --- //
const char* ssid = "OPPO A53";
const char* password = "611b10a883c5";
const char* mqtt_server = "10.74.94.1";

int vel_init = 0;
int vel_last = 0;
int step = 0;
float stepTime = 0.0;
int ciclos = 0;
bool measure_rpm = false;
bool measure_thrust = false;
bool measure_torque = false;
bool measure_current = false;

int estado = STOP;
int estadoAnterior = estado;

float palanca = 6;
float peso = 0.0;
float RPM = 0.0;
float empuje = 0.0;
float par = 0.0;
float consumo = 0.0;

unsigned long pulseInterval;
unsigned long lastPulseTime;
unsigned long now;
unsigned long before;

const float voltToAmp = 0.185;
float escala = 1.0;
float max_current = 0.0;

unsigned int porcentaje = 0;
const unsigned int pwmFreq = 50;
const unsigned int pwmResolution = 16;
unsigned int dutyCycle = 0;
const unsigned int minDuty = 3277;
const unsigned int maxDuty = 6554;


// --- OBJETOS --- //
HX711 balanza1;
HX711 balanza2;
WiFiClient espClient;
PubSubClient client(espClient);
StaticJsonDocument<512> doc;


// --- INTERRUPCIONES --- //
void IRAM_ATTR pulseISR() {
  unsigned long now = micros();
  unsigned long diff = now - lastPulseTime;
  //Si la diferencia entre pulsos consecutivos es mayor a 200 uS, actualizar ultimo pulso
  if (diff > 200) {
    pulseInterval = diff;
    lastPulseTime = now;
  }
}


//--- FUNCION LEER VELOCIDAD ---//
float leerVelocidad() {
  unsigned long intervalo;
  //Desactivar interrupciones
  noInterrupts();
  //Asignar tiempo medido entre pulsos a variable
  intervalo = pulseInterval;
  //Reactivar interrupciones
  interrupts();
  //Si el intervalo es nulo, devolver velocidad == 0
  if (intervalo == 0) {
    return 0.0;
  }
  float revPerSec = 1000000.0f / (float)intervalo;      //Convertir lectura a rev/sec
  return revPerSec * 60.0f;                             //Convertir y devolver lectura en RPM
}


//--- FUNCION GIRAR MOTOR ---//
void giraMotor(int pct) {
  unsigned int duty = map(pct, 0, 100, minDuty, maxDuty);   //Mapear procentaje a velocidad en terminos de duty cicle
  ledcWrite(MOTOR_PIN, duty);                               //Enviar comando PWM al pin conectado con el motor
}


//--- FUNCION LEER CONSUMO ---//
float leerConsumo() {
  long lectura = 0;
  //Bucle para acumular lecturas del sensor de corriente
  for (unsigned int i = 0; i < 10; i++) {
    lectura += analogRead(SENSOR_CORRIENTE);
  }
  lectura /= 10;                                    //Calcular la media de las lecturas
  float volt = (float)lectura * 3.3f / 4095.0f;     //Convertir a valor en voltios (lecturas ADC a voltaje)
  float amp = (volt - 1.435) / voltToAmp;           //Convertir voltios en amperios
  return amp;                                       //devolver corriente estimada
}


//--- FUNCION LEER BALANZA ---//
float leerBalanza(HX711 &balanza) {
  return balanza.get_units(5);            //Promedia 5 lecturas
}


// --- FUNCION CONFIGURAR WIFI --- //
void configWifi() {
  WiFi.mode(WIFI_STA);                        //Configurar modulo Wifi del uC en modo estación
  WiFi.begin(ssid, password);                 //Conectarse con red Wifi indicada
  Serial.print("Conectando a WiFi");
  //Bucle de espera para conectarse a la red Wifi
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }
  Serial.println("WiFi conectado");
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());         //Mostrar ip
}


// --- FUNCION CONFIGURAR MQTT --- //
void configMQTT() {
  client.setBufferSize(2048);           //Configurar tamaño del buffer para recepcion de datos
  client.setServer(mqtt_server, 1883);  //Conectarse a servidor MQTT indicado
  client.setCallback(mqttCallback);     //Añadir funcion de callback asociada a la recepcion de mensajes
}


// --- FUNCION RECONECTAR MQTT --- //
void MQTTreconnect() {
  //Mientras el cliente MQTT no esté conectado, intentar reconectarse y suscribirse al topico de recepcion de datos
  while (!client.connected()) {
    Serial.print("Intentando conexión MQTT...");
    if (client.connect("ESP32")) {
      Serial.println("Conectado al broker MQTT");
      client.subscribe("esp32/input");
    }
  }
}


// --- FUNCION CALLBACK MQTT --- //
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  Serial.println("\n--- MQTT MESSAGE RECEIVED ---");
  Serial.println("LENGTH: " + String(length));
  String jsonStr;                                     //Crear string para almacenar cadena 
  jsonStr.reserve(length + 1);                        //Reservar espacio para string equivalente a la longitud de los datos recibidos + 1
  //Bucle para recorrer caracteres recibidos y añadirlos al string
  for (unsigned int i = 0; i < length; i++) {
    jsonStr += (char)payload[i];
  }
  Serial.print("Topic: ");
  Serial.println(topic);
  Serial.print("Payload: ");
  Serial.println(jsonStr);

  StaticJsonDocument<8192> doc;                                 //Objeto instanciado para trabajar con cadenas en formato JSON
  DeserializationError error = deserializeJson(doc, jsonStr);   //Desserializar cadena y añade error a la variable error si sucede un error
  
  //Si existe algun error, mostrarlo por consola
  if (error) {
    Serial.print("ERROR leyendo JSON: ");
    Serial.println(error.c_str());
    return;
  }

  // Leer acción
  String action = doc["action"] | "";
  Serial.print("Acción recibida: ");
  Serial.println(action);

  //Si la accion es start
  if (action == "start") {
    Serial.println("\n--- CONFIGURACIÓN RECIBIDA ---");
    //Preparar JSON para buscar datos de forma simple
    serializeJsonPretty(doc["data"], Serial);
    //Extraccion de datos y asignacion a variables correspondientes
    vel_init  = doc["data"]["vel_init"].as<int>();
    vel_last  = doc["data"]["vel_last"].as<int>();
    step      = doc["data"]["step"].as<int>();
    stepTime  = doc["data"]["stepTime"].as<float>();
    ciclos    = doc["data"]["cicles"].as<int>();
    measure_rpm     = doc["data"]["measure_rpm"].as<bool>();
    measure_thrust  = doc["data"]["measure_thrust"].as<bool>();
    measure_torque  = doc["data"]["measure_torque"].as<bool>();
    measure_current = doc["data"]["measure_current"].as<bool>();
    max_current = doc["data"]["max_current"].as<float>();

    Serial.println("\n--- VALORES ACTUALIZADOS ---");
    Serial.print("vel_init: "); Serial.println(vel_init);
    Serial.print("vel_last: "); Serial.println(vel_last);
    Serial.print("step: "); Serial.println(step);
    Serial.print("stepTime: "); Serial.println(stepTime);
    Serial.print("cicles: "); Serial.println(ciclos);
    Serial.print("measure_rpm: "); Serial.println(measure_rpm);
    Serial.print("measure_thrust: "); Serial.println(measure_thrust);
    Serial.print("measure_torque: "); Serial.println(measure_torque);
    Serial.print("measure_current: "); Serial.println(measure_current);
    Serial.print("max_current: "); Serial.println(max_current);
    Serial.println("\nVariables internas actualizadas.");

    estado = TESTING;         //Actualizar estado a TESTING
    before = millis();    
    porcentaje = vel_init;    //Asignar velocidad inicial(%)
  }
  //Si la accion es stop, cambiar estado a STOP
  else if (action == "stop") {
    estado = STOP;
  }
  //Si la accion es tare, y el estado actual no es TESTING, cambiar a estado TARE
  else if (action == "tare"){
    if (estado != TESTING){
      estado = TARE;
    }
  }
  //Si la accion es calib, y el estado actual no es TESTING, cambiar a estado CALIB
  else if (action == "calibrate"){
    peso  = doc["data"]["weight"].as<float>();
    if (estado != TESTING){
      estado = CALIB;
    }
  }
  //Si la accion no es ninguna de la anterior, mostrar mensaje
  else {
    Serial.println("Comando no reconocido.");
  }

  Serial.println("--- END MQTT MESSAGE ---\n");
}


// --- FUNCION PUBLICAR MQTT JSON --- //
void JSONpublisher(int porcentaje, float RPM, float consumo, float empuje, float par) {
  doc.clear();                                //Limpiar objeto doc
  doc["%"] = porcentaje;                      //Añadir porcentaje
  doc["RPM"] = RPM;                           //Añadir velocidad medida
  doc["Intensidad"] = consumo;                //Añadir corriente medida
  doc["Empuje"] = empuje;                     //Añadir empuje medido
  doc["Par"] = par;                           //Añadir par medido
  char buffer[256];                           //Buffer para almacenar datos
  size_t n = serializeJson(doc, buffer);      //Serializar datos
  client.publish("esp32/output", buffer, n);  //Publicar datos por MQTT
}


// --- FUNCION CONFIGURAR HX711 --- //
void configHX711() {
  Serial.println("Configurando Celdas de Carga");
  balanza1.begin(DT1, SCK1);        //Iniciar celda de carga 1
  while (!balanza1.is_ready());     
  Serial.println("Celda 1 lista");
  balanza2.begin(DT2, SCK2);        //Iniciar celda de carga 2
  while (!balanza2.is_ready());
  Serial.println("Celda 2 lista");
}


// --- FUNCION INICIAR TEST --- //
void testInit() {
  now = millis();
  //Comprobar tiempo entre pasos
  if ((now - before) >= (stepTime * 1000.0)) {
    before = now;
    //Si se llego a la velocidad final
    if (porcentaje > vel_last) {
      porcentaje = vel_init;    // Reiniciar porcentaje
      giraMotor(porcentaje);    // Detener motor
      delay(1000);
      ciclos--;                 // Restar 1 al contador de ciclos restantes
      Serial.println("TEST FINALIZADO");
      // Si se acabaron los ciclos se pasa a estado de STOP
      if (ciclos == 0){
        estado = STOP;
      }
      return;
    }
    //Si la velocidad (%) no es la final
    if (porcentaje < vel_last + step) {
      Serial.println(porcentaje);
      giraMotor(porcentaje);      // Se gira el motor a la velocidad indicada (%)
      //Si se quiere medir velocidad
      if (measure_rpm){
        RPM = leerVelocidad();
        Serial.print("Velocidad: ");
        Serial.println(RPM);
      }
      //Si se quiere medir empuje
      if (measure_thrust){
        empuje = -leerBalanza(balanza1);
        Serial.print("Empuje: ");
        Serial.println(empuje);
      }
      //Si se quiere medir par
      if (measure_torque){
        par = -leerBalanza(balanza2) * palanca;
        Serial.print("Par: ");
        Serial.println(par);
      }
      //Si se quiere medir corriente
      if (measure_current){
        consumo = leerConsumo();
        //Si el consumo es mayor o igual a la corriente maxima admisible
        if (consumo >= max_current) {
          testStop();         //Detener test
          estado = STOP;      //Cambiar a estado de STOP
          //Publicar mensaje informativo por MQTT
          client.publish("esp32/output","Corriente superior a la máxima");
        }
      }
      // Publicar datos en formato JSON
      JSONpublisher(porcentaje, RPM, consumo, empuje, par);
      Serial.println("DATOS PUBLICADOS");
      //Incrementar velocidad (%)
      porcentaje += step;
    }
  }
}


// --- FUNCION DETENER TEST --- //
void testStop(){
  giraMotor(0);           //Detener giro del motor
  delay(2000);
  //Reseteo de variables
  RPM = 0.0;
  empuje = 0.0;
  par = 0.0;
  consumo = 0.0;
  pulseInterval = 0.0;
}


// --- SETUP --- //
void setup() {
  //Inicio comunicacion serial
  Serial.begin(115200);
  while (!Serial){;}
  //Configuracion conexion wifi
  configWifi();
  //Configuracion comunicacion MQTT
  configMQTT();
  //Configuracion de pines
  pinMode(TACOMETRO, INPUT_PULLUP);
  pinMode(SENSOR_CORRIENTE, INPUT);
  //Declaracion de interrupcion
  attachInterrupt(digitalPinToInterrupt(TACOMETRO), pulseISR, FALLING);
  //Configurar celdas de carga
  configHX711();
  //Configurar motor y PWM
  ledcAttach(MOTOR_PIN, pwmFreq, pwmResolution);
  ledcWrite(MOTOR_PIN, map(0, 0, 100, minDuty, maxDuty));
  delay(5000);
  //Comenzar ensayo motor detenido
  testStop();
}


// --- LOOP --- //
void loop() {
  //Si no hay cliente MQTT conectado, intentar reconectar
  if (!client.connected()) {
    MQTTreconnect();
  }
  //Mantener cliente MQTT activo
  client.loop();

  //Maquina de estados
  switch (estado) {
    //Estado de STOP
    case STOP:
      testStop();
      if (estadoAnterior != STOP){
        Serial.println("STOPPED");
      }
      break;

    //Estado de TESTING
    case TESTING:
      if (estadoAnterior != TESTING){
        Serial.println("TESTING");
      }
      testInit();
      break;

    //Estado de TARE
    case TARE:
      balanza1.tare(20);          //Tarar celda de carga 1
      Serial.println("TARA 1");
      balanza2.tare(20);          //Tarar celda de carga 2
      Serial.println("TARA 2");
      estado = STOP;              //Cambiar estado a STOP
      client.publish("esp32/output","Tara Realizada");
      break;

    //Estado de CALIB
    case CALIB:
      balanza1.set_scale();       //Escalar celda de carga con escala = 1
      delay(1000);
      Serial.println(peso);
      escala = balanza1.get_value(10) / peso;   //Calcular escalar celda de carga 1
      balanza1.set_scale(escala);               //Escalar celda de carga 1  
      balanza2.set_scale(escala);               //Escalar celda de carga 2
      Serial.println("CALIBRADA 1 y 2");
      estado = STOP;                            //Cambiar estado STOP
      client.publish("esp32/output","Calibración Realizada");
      break;
  }
  estadoAnterior = estado;       //Actualizar estado anterior
}