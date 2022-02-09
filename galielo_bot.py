import requests
import logging
import os
import telegram
from telegram import *
from telegram.ext import Updater, CallbackContext, CommandHandler, CallbackQueryHandler

#Switch between local and online behaviour
ONLINE = True

TOKEN = open("TOKEN.txt", "r").read()
#Heroku-only variables
PORT = int(os.environ.get("PORT")) if ONLINE else 0
APP_PATH = "https://galielobot.herokuapp.com/"
#API variables
BASE_URL = "http://galielo.altervista.org/api/"
STAT_URL = "http://galielo.altervista.org/elo/player_stats.php?id="
strings = ["Select the winning team's attacker",
           "Select the winning team's defender",
           "Select the losing team's attacker",
           "Select the losing team's defender"]
other_str = ["Show inactive players >>", "<< Show active players", "<-- Back", "Search —○"]
plr_names_db = []
#to be used only for name searches. It is updated once a user starts a new search
btns_per_line = 2
#max number of buttons that can be visualized by the Telegram client
#TODO: check that there are no more than that in a message...
#MAX_NUM_BUTTONS = 100

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",level=logging.INFO)
logger = logging.getLogger(__name__)

#TODO:
#-search for players' names

def sort_names(rule_out=[], total=False):
    data = players()
    output = data[:]
    for i in range(len(data)):
        for j in range(i + 1, len(data)):
            if output[i]["Nome"] < output[j]["Nome"]:
                swap = output[i]
                output[i] = output[j]
                output[j] = swap
    #now players are in reverse alphabetical order
    if total:
        # we want two lists, made of players inactive/active
        inact, act = [],[]
        for i in range(len(output)):
            if str(output[i]["ID"]) not in rule_out:
                if output[i]["CountRecentA"] + output[i]["CountRecentD"] <= 10:
                    inact.append(output[i])
                else:
                    act.append(output[i])
        return [inact, act]
    else:
        # we want four lists, made of players inactive/active in attack/defense
        atk_inact, atk_act, def_inact, def_act = [],[],[],[]
        for i in range(len(output)):
            if str(output[i]["ID"]) not in rule_out:
                if output[i]["CountRecentA"] <= 10:
                    atk_inact.append(output[i])
                else:
                    atk_act.append(output[i])
                if output[i]["CountRecentD"] <= 10:
                    def_inact.append(output[i])
                else:
                    def_act.append(output[i])
        return [atk_inact, atk_act, def_inact, def_act]

def players():
    res = requests.get(BASE_URL + "player.php")
    return res.json()

def plr_stats(plr_id):
    res = requests.get(BASE_URL + "player.php?id=" + str(plr_id))
    return res.json()

def matches():
    res = requests.get(BASE_URL + "match.php")
    return res.json()

def plr_names(plr_ids):
    plrs = players()
    return [[p["Nome"] for p in plrs if str(p["ID"]) == str(var)][0] for var in plr_ids]

def plr_format(datas):
    names = []
    if len(datas) >= 9:
        names = plr_names(datas[:4])
        names = [names[i] + f" ({str(datas[5+i])})" for i in range(4)]
    else:
        names = plr_names(datas[:4])
        names = names + max(0, 4-len(datas)) * ["?"]
    points = datas[4] if len(datas) >= 5 else "?"
    l = max(len(names[0]), len(names[1]), len(names[2]), len(names[3]), 8)
    return f"`{names[0]:<{l}}\n{names[1]:<{l}}\n{'└ 10-'+str(points)+' ┐':^{l}}\n{names[2]:<{l}}\n{names[3]:<{l}}`"

def add_match(atk_win, def_win, atk_lose, def_lose, points):
    params = {"add":True,"att1":atk_win,"att2":atk_lose,"dif1":def_win,"dif2":def_lose,"pt1":10,"pt2":points}
    res = requests.post(url = BASE_URL+"match.php?", data = params)
    return res.json()

def del_match():
    requests.post(url = BASE_URL+"match.php?", data = {"delete":True})



def start_command(update: Update, context: CallbackContext):
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text="Welcome to the GaliELO bot! Here you can rank your games and review your points. Click /rank to insert a new game.")

def rank_command(update: Update, context: CallbackContext):
    #start the ranking process, which is then continued by rank_callback on subsequent clicks
    plr_list = sort_names()[:]
    
    btns = [InlineKeyboardButton(text=p["Nome"], callback_data=str(p["ID"])+"_0") for p in plr_list[1]]
    keyboard = [btns[i : i+btns_per_line] for i in range(0, len(btns), btns_per_line)]
    other = InlineKeyboardButton(text=other_str[0], callback_data="sh_ina_atk_0")
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text=plr_format([])+"\n\n"+strings[0],
                             parse_mode=telegram.ParseMode.MARKDOWN_V2,
                             reply_markup=InlineKeyboardMarkup([[other]] + keyboard))

def delete_command(update: Update, context: CallbackContext):
    last = matches()[-1]
    message_str = plr_format([last["Att1"], last["Dif1"], last["Att2"], last["Dif2"], last["Pt2"]])
    keyboard = [[InlineKeyboardButton(text="Yes", callback_data=str(last["ID"])+"_del_yes"),
                 InlineKeyboardButton(text="No", callback_data="del_no")]]
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text=message_str+"\n\nAre you sure that you want to delete this match?",
                             parse_mode=telegram.ParseMode.MARKDOWN_V2,
                             reply_markup=InlineKeyboardMarkup(keyboard))

def stats_command(update: Update, context: CallbackContext):
    plr_list = sort_names(total=True)[:]
    btns = [InlineKeyboardButton(text=p["Nome"], callback_data=str(p["ID"])+"_stat") for p in plr_list[1]]
    keyboard = [btns[i : i+btns_per_line] for i in range(0, len(btns), btns_per_line)]
    other = InlineKeyboardButton(text=other_str[0], callback_data="sh_ina_stat")
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text="Choose a player:",
                             reply_markup=InlineKeyboardMarkup([[other]] + keyboard))
    
def rank_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data

    if "del" in data:
        #user wants to delete a match
        if "yes" in data:
            m_id = data[:-8]
            last = matches()[-1]
            if str(last["ID"]) == m_id:
                del_match()
                message_str = plr_format([last["Att1"], last["Dif1"], last["Att2"], last["Dif2"], last["Pt2"]])
                query.edit_message_text(text=message_str+"\n\nMatch deleted\.",
                                        parse_mode=telegram.ParseMode.MARKDOWN_V2)
            else:
                query.edit_message_text(text="Aborted: the last match in the database at present time is different from the one you selected.")
        else:
            query.edit_message_text(text="No match deleted.")
    elif "stat" in data:
        #user is choosing a player whose stats to visualize
        if "sh" in data:
            #user changed category to visualize
            plr_list = sort_names(total=True)[:]
            act_index = 0 if "ina" in data else 1               #0 -> show inactive, 1 -> show active
            
            btns = [InlineKeyboardButton(text=p["Nome"], callback_data=str(p["ID"])+"_stat") for p in plr_list[act_index]]
            keyboard = [btns[i : i+btns_per_line] for i in range(0, len(btns), btns_per_line)]

            act_index = 1-act_index
            
            other = InlineKeyboardButton(text=other_str[act_index], callback_data=f"sh_{'act' if act_index else 'ina'}_stat")
            query.edit_message_text(text="Choose a player:",
                                    reply_markup=InlineKeyboardMarkup([[other]] + keyboard))
        else:
            #show statistics
            s = data[:-5]
            stat = plr_stats(s)
            stat_text = f"`{stat['Nome']}\n\nAttack:    {stat['PuntiA']}\nDefense:   {stat['PuntiD']}\nAverage:   {(int(stat['PuntiA']) + int(stat['PuntiD'])) / 2.0:g}`"
            query.edit_message_text(text=stat_text+f"\n\nFor more info click [here]({STAT_URL+s})\.",
                                    parse_mode=telegram.ParseMode.MARKDOWN_V2)
    else:
        #user is ranking a match
        if "sh" in data:
            #user changed category to visualize
            s = data[:-12] if len(data) > 12 else ""
            s_formatted = s+"," if len(s) > 0 else ""
            rule_out = data[:-12].split(",") if len(data) > 12 else []
            str_formatted = plr_format(rule_out)+"\n\n"
            plr_list = sort_names(rule_out)[:]

            step = int(data[-1])
            act_index = 0 if "ina" in data else 1               #0 -> show inactive, 1 -> show active
            def_index = 0 if "atk" in data else 1               #0 -> attack, 1 -> defense
            plr_index = 2 * def_index + act_index               #0 -> inactive attack, 1 -> active attack, 2 -> inactive defense, 3 -> active defense

            act_index = 1 - act_index
            
            callback_str = f"sh_{'act' if act_index else 'ina'}_{'def' if def_index else 'atk'}_{str(step)}"
            
            btns = [InlineKeyboardButton(text=p["Nome"], callback_data=s_formatted+str(p["ID"])+"_"+str(step)) for p in plr_list[plr_index]]
            keyboard = [btns[i : i+btns_per_line] for i in range(0, len(btns), btns_per_line)]
            other1 = InlineKeyboardButton(text=other_str[2], callback_data=s+"_back_"+str(step))
            other2 = InlineKeyboardButton(text=other_str[0], callback_data=s+"sh_ina_"+("def" if def_index else "atk")+"_"+str(step))
            other = [[other1], [other2]] if step > 0 else [[other2]]
            query.edit_message_text(text=str_formatted+strings[step],
                                    parse_mode=telegram.ParseMode.MARKDOWN_V2,
                                    reply_markup=InlineKeyboardMarkup(other + keyboard))
        elif "_sc" in data:
            #all datas entered, rank the match
            datas = data[:-3].split(",")
            res = add_match(int(datas[0]), int(datas[1]), int(datas[2]), int(datas[3]), int(datas[4])) #add the game to the database!
            if res["success"]:
                #send confirm message
                var_points = [str(res["VarA1"]), str(res["VarD1"]), str(res["VarA2"]), str(res["VarD2"])]
                mex_text = "Match added:\n\n" + plr_format(datas + var_points)
                if res["ccup"]:
                    mex_text = mex_text + "\n\nThe champion cup has been updated!"
                query.edit_message_text(text=mex_text,
                                        parse_mode=telegram.ParseMode.MARKDOWN_V2)
            else:
                #send error message
                mex_text = f"Match not added:\n\n`{str(res['error_message'])}`"
                query.edit_message_text(text=mex_text,
                                        parse_mode=telegram.ParseMode.MARKDOWN_V2)
        else:
            #we are in the process of selecting players and score
            s = ""
            rule_out = []
            step = 0
            if "back" in data:
                #user chose to go back
                step = int(data[-1]) - 1
                rule_out = data[:-7].split(",")[:-1]
                s = ",".join(rule_out)
            else:
                #go on
                s = data[:-2]
                rule_out = s.split(",")
                step = int(data[-1]) + 1
            
            s_formatted = s+"," if len (s) > 0 else ""
            plr_list = sort_names(rule_out)[:]
            if step == 4:
                #all players selected, ask the score
                points_keyboard = [[InlineKeyboardButton(text=other_str[2], callback_data=s+"_back_4")]] + [[InlineKeyboardButton(text="10:"+str(i), callback_data=s+","+str(i)+"_sc")] for i in range(10)]
                query.edit_message_text(text=plr_format(rule_out)+"\n\n"+"What was the score?",
                                        parse_mode=telegram.ParseMode.MARKDOWN_V2,
                                        reply_markup=InlineKeyboardMarkup(points_keyboard))
            else:
                #ask the next player
                def_index = step % 2                            #0 -> attack, 1 -> defense
#                                                      this is because we always want to show active players at this point -> \_______________
                btns = [InlineKeyboardButton(text=p["Nome"], callback_data=s_formatted+str(p["ID"])+"_"+str(step)) for p in plr_list[2*def_index + 1]]
                keyboard = [btns[i : i+btns_per_line] for i in range(0, len(btns), btns_per_line)]
                other1 = InlineKeyboardButton(text=other_str[2], callback_data=s+"_back_"+str(step))
                other2 = InlineKeyboardButton(text=other_str[0], callback_data=s+"sh_ina_"+("def" if def_index else "atk")+"_"+str(step))
                other = [[other1], [other2]] if step > 0 else [[other2]]
                query.edit_message_text(text=plr_format(rule_out)+"\n\n"+strings[step],
                                        parse_mode=telegram.ParseMode.MARKDOWN_V2,
                                        reply_markup=InlineKeyboardMarkup(other + keyboard))
    #everything done, answer the query
    query.answer()


def error_handler(update: Update, context: CallbackContext):
    #logger.warning('Update "%s" caused error "%s"', update, context.error)
    logger.exception(context.error)
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text=f"Error:\n\n`{context.error}`",
                             parse_mode=telegram.ParseMode.MARKDOWN_V2)
        
updater = Updater(token='5255537406:AAEHfU30jmjDtY2QXyYR8UQADHKSpIsa324', use_context=True)
dispatcher = updater.dispatcher

dispatcher.add_handler(CommandHandler('start', start_command))
dispatcher.add_handler(CommandHandler('rank', rank_command))
dispatcher.add_handler(CommandHandler('delete', delete_command))
dispatcher.add_handler(CommandHandler('stats', stats_command))
dispatcher.add_handler(CallbackQueryHandler(rank_callback))
dispatcher.add_error_handler(error_handler)

if ONLINE:
    #Create and start a webhook, so that the bot can be put to sleep when not in use, if you are running on Heroku
    updater.start_webhook(listen="0.0.0.0", port=PORT, url_path=TOKEN, webhook_url=APP_PATH + TOKEN)
    updater.idle()
else:
    #Start polling if you are running in local
    updater.start_polling()
    
    
    
