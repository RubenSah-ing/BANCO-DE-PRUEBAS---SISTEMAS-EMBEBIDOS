#----- LIBRERIAS -----#
from flask import Flask, render_template, request, jsonify
import json
from lib.TestBech import TestBench


#---- MOSQUITTO ----#
topicReceive = "esp32/output"
topicSend = "esp32/input"
broker_IP = "10.74.94.63"
broker_PORT = 1883
mosquitto_path = r"C:\\Program Files\\mosquitto\\mosquitto.exe"
mosquitto_conf = r"C:\\Program Files\\mosquitto\\mosquitto.conf"


# ----- INSTANCIA TESTBENCH ----- #
tb = TestBench()
# Metodo para configurar broker MQTT
tb.configMQTTBroker(broker_IP, broker_PORT, mosquitto_path, mosquitto_conf)
# Metodo para configurar comunicacion MQTT
tb.configMQTT(topicSend=topicSend, topicReceive=topicReceive)


#----- OBJETOS -----#
app = Flask(__name__)

#----- VARIABLES -----#
topicReceive = "esp32/output"
topicSend = "esp32/input"
broker_IP = "10.251.249.1"
broker_PORT = 1883
mosquitto_path = r"C:\Program Files\mosquitto\mosquitto.exe"
mosquitto_conf = r"C:\Program Files\mosquitto\mosquitto.conf"
latest_data = {"velocity": [], "thrust": [], "torque": [], "current": []}
config = None
client = None
porcentaje, velocidad, empuje, par, corriente = [], [], [], [], []


# ----- FUNCION AUXILIAR PARA ENVIAR MENSAJES MQTT ----- #
def send_action(action, data=None):
    payload = {"action": action}
    if data:
        payload["data"] = data
    tb.sendMQTT(tb.topicSend, json.dumps(payload))


#----- RUTA PRINCIPAL -----#
@app.route('/', methods=['GET', 'POST'])
def index():
    global config

    if request.method == 'POST':
        action = request.form.get('action')
        print(f"Acción recibida: {action}")
        tb._running = True

        if action == 'start':
            propeller = request.form.get('propName')
            pitch = request.form.get('pitch', type=float)
            diameter = request.form.get('diameter', type=float)
            motor = request.form.get('motorName')
            kv = request.form.get('kv', type=float)
            max_current = request.form.get('maxCurrent', type=float)
            print(f"Corriente maxima {max_current}")
            config = {"propName": propeller,
                      "diameter": diameter,
                      "pitch": pitch,
                      "motorName": motor,
                      "kv": kv,
                      "max_current": max_current,
                      "testName": request.form.get('testName'),
                      "vel_init": request.form.get('vel_init', type=float),
                      "vel_last": request.form.get('vel_last', type=float),
                      "stepTime": request.form.get('stepTime', type=float),
                      "step": request.form.get('step', type=int),
                      "cicles": request.form.get('cicles', type=int),
                      "measure_rpm": 'measure_rpm' in request.form,
                      "measure_thrust": 'measure_thrust' in request.form,
                      "measure_torque": 'measure_torque' in request.form,
                      "measure_current": 'measure_current' in request.form
                    }

            print("Configuración enviada con START:")
            # Metodo para setear informacion acerca del ensayo
            tb.setTestInfo(propeller, pitch, diameter, motor, kv, max_current)
            # Metodo para introducir parametros del ensayo
            tb.setTestConfig(config)
            # Metodo para enviar accion y datos al banco de pruebas
            send_action("start", config)
            print("Ensayo iniciado")

        elif action == 'calibrate':
            weight = request.form.get('weight', type=float)
            config = {"weight":weight}
            print(f"Ejecutando {config})")
            send_action("calibrate", config)

        elif action == 'tare':
            print(f"Ejecutando tare: ")
            send_action("tare")
        
        elif action == 'stop':
            print(f"Ejecutando stop: ")
            send_action("stop")

    return render_template('index.html')



#----- MAIN -----#
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)