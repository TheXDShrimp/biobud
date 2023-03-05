import time
import json
import base64
import asyncio
import websockets
import pyaudio
import os
from flask import render_template, request, Response, jsonify
from werkzeug.utils import redirect
from app import app, APP_ROOT
from datetime import datetime
from pydub import AudioSegment
from pydub.playback import play
from gtts import gTTS
import playsound

import openai
openai.api_key = "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"

auth_key = '4ea3ef3cfc8147bf92058044dce13ef0'


def get_gpt_prediction(transcript, query):
    completion = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a physician answering a doctor's questions during a patient visit using the transcript. Be concise."},
            {"role": "user", "content": f"Transcript between doctor and patient without labels: {transcript}\nQuestion: {query}"}
        ]
    )

    return completion['choices'][0]['message']['content']


FRAMES_PER_BUFFER = 3200
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
p = pyaudio.PyAudio()

transcript = ""
stream = None

stream = p.open(
    format=FORMAT,
    channels=CHANNELS,
    rate=RATE,
    input=True,
    frames_per_buffer=FRAMES_PER_BUFFER
)

# the AssemblyAI endpoint we're going to hit
URL = "wss://api.assemblyai.com/v2/realtime/ws?sample_rate=16000"


async def send_receive():
    print(f'Connecting websocket to url ${URL}')
    async with websockets.connect(
        URL,
        extra_headers=(("Authorization", auth_key),),
        ping_interval=5,
        ping_timeout=20
    ) as _ws:
        await asyncio.sleep(0.1)
        print("Receiving SessionBegins ...")
        session_begins = await _ws.recv()
        print(session_begins)
        print("Sending messages ...")

        f = open("stt.txt", "w")

        async def send():
            while True:
                try:
                    if "exit" in transcript[-10:]:
                        return

                    data = stream.read(FRAMES_PER_BUFFER)
                    data = base64.b64encode(data).decode("utf-8")
                    json_data = json.dumps({"audio_data": str(data)})
                    await _ws.send(json_data)
                except websockets.exceptions.ConnectionClosedError as e:
                    print(e)
                    assert e.code == 4008
                    break
                except Exception as e:
                    return
                await asyncio.sleep(0.01)

            return True

        async def receive(transcript: str):
            while True:
                try:
                    result_str = await _ws.recv()
                    tmp: str = json.loads(result_str)['text']
                    if not tmp.strip() and transcript.strip() or tmp.lower().replace('.', '').replace(',', '')[:5] != transcript.lower().replace('.', '').replace(',', '')[:5]:
                        f.write(transcript + "\n")

                    transcript = tmp
                    print(transcript)

                    if "exit" in transcript[-10:]:
                        await _ws.close()
                        return transcript
                except websockets.exceptions.ConnectionClosedError as e:
                    print(e)
                    assert e.code == 4008
                    break
                except Exception as e:
                    print("RECEIVE ERROR")
                    print(e)
                    # assert False, "Not a websocket 4008 error"

        send_result, receive_result = await asyncio.gather(send(), receive(transcript))
        # print("Internal result:", receive_result)

        return receive_result


def transcribe():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(send_receive())
    finally:
        loop.close()


@app.route('/')
def home():
    return render_template('index.html', title='Home')


@app.route('/record', methods=['GET', 'POST'])
def record():
    if request.method == 'POST':
        # print('bob')
        # transcribe
        transcribe()
        # get prediction
        transcript_txt = open('stt.txt', 'r').read().lower()
        transcript = '\n'.join(transcript_txt.split('hey bio bud')[:-1])
        query = transcript_txt.split('hey bio bud')[-1]
        prediction = get_gpt_prediction(transcript, query)
        
        open('gptOutput.txt', 'w').write(prediction)

        # sound = AudioSegment.from_wav(
        #     os.path.join(APP_ROOT, 'static', 'tts.wav'))
        # play(sound)

        # read the words from a file and turn it into a string

        tts = gTTS(prediction, lang='en')
        tts.save(os.path.join(APP_ROOT, 'static', 'tts.mp3'))

        playsound.playsound(os.path.join(APP_ROOT, 'static', 'tts.mp3'), True)


        # print(3)

        # return prediction
        return render_template('record.html', title='BioBud', btn_class='stop', btn_text='Stop Recording')
    else:
        return render_template('record.html', title='BioBud', btn_class='start', btn_text='Start Recording')


@app.route('/time')
def get_time():
    return jsonify({'time': time.time()})
