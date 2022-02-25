import logging
import os
import requests
import signal
import status_observer as so #local module that changes bot's description when it goes down
import sys
import telegram
from telegram import *
from telegram.ext import Updater, CallbackContext, CommandHandler, CallbackQueryHandler, InlineQueryHandler

#switch between local and online behaviour
ONLINE = True
if os.path.expanduser("~").startswith("/home"):
    ONLINE = False

f = open("TOKEN.txt", "r")
TOKEN = f.readline()[:-1]   #leave out the newline character
f.close()

#Heroku-only variables
PORT = 0
if ONLINE:
    PORT = int(os.environ.get("PORT"))
APP_PATH = "https://galielobot.herokuapp.com/"
#API variables
BASE_URL = "http://galielo.altervista.org/api/"
STAT_URL = "http://galielo.altervista.org/elo/player_stats.php?id="

#general datas of the bot
strings = ["Select the winning team's attacker",
           "Select the winning team's defender",
           "Select the losing team's attacker",
           "Select the losing team's defender"]
other_str = ["Show inactive players >>",
             "<< Show active players",
             "<-- Back",
             "Search —○"]
btns_per_line = 2
#max number of buttons that can be visualized by the Telegram client
#TODO: check that there are no more than that in a message...
#MAX_NUM_BUTTONS = 100



logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",level=logging.INFO)
logger = logging.getLogger(__name__)



def show_menu(params, category, mess_id):
    #return the text and keyboard markup associated with the specified parameters and category to be shown (0/1 for active/inactive); mess_id is the id of the message to be sent
    #in case all parameters are given, ranks the match

    if len(params) < 4:
        #choose next player

        s = ",".join(params) if len(params) > 0 else ""
        s_formatted = s+"," if len(s) > 0 else ""
        #list of chosen players, to be ruled out from future choices
        rule_out = params[:max(4, len(params))] if len(params) > 0 else []
        #ASCII art representing the present match
        str_formatted = plr_format(rule_out)+"\n\n"
        #list of valid players
        plr_list = sort_names(rule_out)[:]

        step = len(params)                                  #0 -> winning attack, 1 -> winning defense, 2 -> losing attack, 3 -> losing defense
        def_index = step % 2                                #0 -> attack, 1 -> defense

        #callback data for the active/inactive button
        callback_str = f"sh_{'ina' if category else 'act'}_{'def' if def_index else 'atk'}_{str(step)}"

        #list of buttons for the players
        btns = [InlineKeyboardButton(text=p["Nome"],
                                     callback_data=s_formatted+str(p["ID"])+"_"+str(step)) for p in plr_list[2*def_index + (1-category)]]
        #arrange the buttons in rows
        keyboard = [btns[i : i+btns_per_line] for i in range(0, len(btns), btns_per_line)]
        #search offset string
        search_offset = "rank "+str(mess_id)+(","+s if len(s) > 0 else "")+" "
        #extra buttons
        back_btn = InlineKeyboardButton(text=other_str[2],
                                        callback_data=s+"_back_"+str(step))
        other_cat = InlineKeyboardButton(text=other_str[category],
                                         callback_data=s+callback_str)
        search_button = InlineKeyboardButton(text=other_str[3],
                                             switch_inline_query_current_chat=search_offset)
        #compose the upper part of the keyboard --- the search button is at the bottom
        other = [[back_btn], [other_cat]] if step > 0 else [[other_cat]]
        return [str_formatted+strings[step],
                InlineKeyboardMarkup(other + keyboard + [[search_button]])]
    elif len(params) == 4:
        #choose the score
        s = ",".join(params)
        back_btn = InlineKeyboardButton(text=other_str[2],
                                        callback_data=s+"_back_4")
        points_keyboard = [[back_btn]] + [[InlineKeyboardButton(text="10:"+str(i),
                                                                callback_data=s+","+str(i)+"_sc")] for i in range(10)]
        return [plr_format(params[:4])+"\n\n"+"What was the score?",
                InlineKeyboardMarkup(points_keyboard)]

    elif len(params) == 5:
        #rank the match and show results

        #add the game to the database!
        res = add_match(int(params[0]), int(params[1]), int(params[2]), int(params[3]), int(params[4]))
        if res["success"]:
            #send confirm message
            var_points = [str(res["VarA1"]), str(res["VarD1"]), str(res["VarA2"]), str(res["VarD2"])]
            mex_text = "Match added:\n\n" + plr_format(params + var_points)
            if res["ccup"]:
                mex_text = mex_text + "\n\nThe champion cup has been updated!"
            return [mex_text, None]
        else:
            #send error message
            return [f"Match not added:\n\n`{str(res['error_message'])}`", None]
    else:
        #show some error
        return ["Error, too many paramaters.", None]

def sort_names(rule_out=[], total=False):
    #return two or four (depending on total) lists of players ordered by reverse alphabetical order
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

def check_query(q):
    #check that the string q is a representation of a list of numbers with 1 <= len <= 4
    #the first parameter should be the ID of a message and the others IDs of players
    #TODO: check that the latter effectively holds
    dummy = q.replace(",", "")
    if dummy.isnumeric():
        #check that the data are correct
        dummy = q.split(",")
        if len(dummy) >= 1 and len(dummy) <= 5:
            # mess_id = dummy[0]
            # data = dummy[1:]
            # try:
            #
            # except:
            #     return False
            return True
    return False


def players():
    #return a list of all the players
    res = requests.get(BASE_URL + "player.php")
    return res.json()

def plr_stats(plr_id):
    #return a list of basic stats of the player having plr_id as ID
    res = requests.get(BASE_URL + "player.php?id=" + str(plr_id))
    return res.json()

def matches():
    #return a list of all visible matches in the database
    res = requests.get(BASE_URL + "match.php")
    return res.json()

def plr_names(plr_ids):
    #return the names of the players having plr_id as ID
    plrs = players()
    return [[p["Nome"] for p in plrs if str(p["ID"]) == str(var)][0] for var in plr_ids]

def plr_format(datas):
    #return a human-readable string for the match represented by the list datas --- the format expected for datas is:
    #
    #   0-3: IDs of the players (winning attacker, winning defender, losing attacker, losing defender)
    #   4: score of the losing team
    #   5-8: point variation of the players involved after the match
    #
    #any number of parameters can be provided, the empty spots will be filled by "?"s
    names = []
    if len(datas) >= 9:
        #if point variations have been provided, display them next to the names
        names = plr_names(datas[:4])
        names = [names[i] + f" ({str(datas[5+i])})" for i in range(4)]
    else:
        names = plr_names(datas[:4])
        names = names + max(0, 4-len(datas)) * ["?"]
    points = datas[4] if len(datas) >= 5 else "?"
    l = max(len(names[0]), len(names[1]), len(names[2]), len(names[3]), 8)
    return f"`{names[0]:<{l}}\n{names[1]:<{l}}\n{'└ 10-'+str(points)+' ┐':^{l}}\n{names[2]:<{l}}\n{names[3]:<{l}}`"

def add_match(atk_win, def_win, atk_lose, def_lose, points):
    #add the match specifed by the parameters to the database
    params = {"add":True,"att1":atk_win,"att2":atk_lose,"dif1":def_win,"dif2":def_lose,"pt1":10,"pt2":points}
    res = requests.post(url = BASE_URL+"match.php?", data = params)
    return res.json()

def del_match():
    #delete last match from the database
    requests.post(url = BASE_URL+"match.php?", data = {"delete":True})



def start_command(update: Update, context: CallbackContext):
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text="Welcome to the GaliELO bot! Here you can rank your games and review your points. Click /rank to insert a new game.")

def rank_command(update: Update, context: CallbackContext):
    #start the ranking process, which is then continued by rank_callback on subsequent clicks

    res = show_menu([], 0, update.message.message_id+1)
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text=res[0],
                             parse_mode=telegram.ParseMode.MARKDOWN_V2,
                             reply_markup=res[1])

def delete_command(update: Update, context: CallbackContext):
    last = matches()[-1]
    message_str = plr_format([last["Att1"], last["Dif1"], last["Att2"], last["Dif2"], last["Pt2"]])
    keyboard = [[InlineKeyboardButton(text="Yes",
                                      callback_data=str(last["ID"])+"_del_yes"),
                 InlineKeyboardButton(text="No",
                                      callback_data="del_no")]]
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text=message_str+"\n\nAre you sure that you want to delete this match?",
                             parse_mode=telegram.ParseMode.MARKDOWN_V2,
                             reply_markup=InlineKeyboardMarkup(keyboard))

def stats_command(update: Update, context: CallbackContext):
    plr_list = sort_names(total=True)[:]
    btns = [InlineKeyboardButton(text=p["Nome"],
                                 callback_data=str(p["ID"])+"_stat") for p in plr_list[1]]
    keyboard = [btns[i : i+btns_per_line] for i in range(0, len(btns), btns_per_line)]
    other_cat = InlineKeyboardButton(text=other_str[0],
                                 callback_data="sh_ina_stat")
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text="Choose a player:",
                             reply_markup=InlineKeyboardMarkup([[other_cat]] + keyboard))

def last5_command(update: Update, context: CallbackContext):
    #show the last 5 ranked matches
    matches_list = matches()[-5:]
    res = "Last 5 matches present in the database:\n\n\n`"
    matches_strings = []
    length = 0
    for m in matches_list:
        cur_str = str(m["Timestamp"]) + "\n\n" + plr_format([m["Att1"], m["Dif1"], m["Att2"], m["Dif2"], m["Pt2"]]).replace("`", "")
        matches_strings.append(cur_str)
        for s in cur_str.split("\n"):
            length = len(s) if len(s) > length else length
    for i in range(4):
        res = res + matches_strings[i] + "\n\n" + "\-"*length + "\n\n"
    res = res + matches_strings[4] + "`"
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text=res,
                             parse_mode=telegram.ParseMode.MARKDOWN_V2)

def proc_command(update: Update, context: CallbackContext):
    #hidden command to process the choice of player with the "Search" function
    values = update.message.text.split(" ")[1]
    params = values.split(",")
    mess_id = int(params[0])
    res = show_menu(params[1:], 0, mess_id)
    #delete the last message sent to the bot
    context.bot.delete_message(update.message.chat.id, update.message.message_id)
    #edit the message specified by mess_id
    context.bot.edit_message_text(chat_id=update.message.chat.id,
                                  message_id=mess_id,
                                  text=res[0],
                                  parse_mode=telegram.ParseMode.MARKDOWN_V2,
                                  reply_markup=res[1])

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

            btns = [InlineKeyboardButton(text=p["Nome"],
                                         callback_data=str(p["ID"])+"_stat") for p in plr_list[act_index]]
            keyboard = [btns[i : i+btns_per_line] for i in range(0, len(btns), btns_per_line)]

            act_index = 1-act_index

            other_cat = InlineKeyboardButton(text=other_str[act_index],
                                         callback_data=f"sh_{'act' if act_index else 'ina'}_stat")
            query.edit_message_text(text="Choose a player:",
                                    reply_markup=InlineKeyboardMarkup([[other_cat]] + keyboard))
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
            params = data[:-12].split(",") if len(data) > 12 else []
            act_index = 0 if "ina" in data else 1               #0 -> show inactive, 1 -> show active

            res = show_menu(params, act_index, query.message.message_id)

            query.edit_message_text(text=res[0],
                                    parse_mode=telegram.ParseMode.MARKDOWN_V2,
                                    reply_markup=res[1])
        elif "_sc" in data:
            #all datas entered, rank the match
            params = data[:-3].split(",")
            res = show_menu(params, 0, query.message.message_id)
            query.edit_message_text(text=res[0],
                                    parse_mode=telegram.ParseMode.MARKDOWN_V2,
                                    reply_markup=res[1])
        else:
            #we are in the process of selecting players and score
            params = []
            if "back" in data:
                #user chose to go back
                params = data[:-7].split(",")[:-1]
            else:
                #go on
                params = data[:-2].split(",")

            res = show_menu(params, 0, query.message.message_id)

            query.edit_message_text(text=res[0],
                                    parse_mode=telegram.ParseMode.MARKDOWN_V2,
                                    reply_markup=res[1])
    #everything done, answer the query
    query.answer()


def search_handler(update: Update, context: CallbackContext):
    query = update.inline_query.query

    show_stats = True    #dummy variable to show stats of a player if the user is outside of the chat with the bot or datas are corrupt

    res = []
    if update.inline_query.chat_type == telegram.Chat.SENDER:
        #check if we are ranking a game
        if "rank " in query:
            #separate the parts of the query and proceed
            query_parts = query.split(" ")
            s = ""
            if len(query_parts) > 2:
                #check if the data are correct
                if check_query(query_parts[1]):
                    params = query_parts[1][:].split(",")
                    for p in players():
                        if query_parts[-1].lower() in p["Nome"].lower() and str(p["ID"]) not in params[1:]:
                            res.append(InlineQueryResultArticle(id=p["ID"],
                                                                title=p["Nome"],
                                                                input_message_content=InputTextMessageContent(message_text="/proc "+query_parts[1]+","+str(p["ID"]))))
    if show_stats:
        #show stats if search result is selected
        for p in players():
            if query.lower() in p["Nome"].lower():
                stat = plr_stats(p["ID"])
                stat_text = (f"`{stat['Nome']}\n\n"
                            f"Attack:    {stat['PuntiA']}\n"
                            f"Defense:   {stat['PuntiD']}\n"
                            f"Average:   {(int(stat['PuntiA']) + int(stat['PuntiD'])) / 2.0:g}`")
                res.append(InlineQueryResultArticle(id=p["ID"],
                                                    title=p["Nome"],
                                                    input_message_content=InputTextMessageContent(message_text=stat_text+f"\n\nFor more info click [here]({STAT_URL+str(p['ID'])})\.",
                                                                                                  parse_mode=telegram.ParseMode.MARKDOWN_V2)))
    update.inline_query.answer(res)

def error_handler(update: Update, context: CallbackContext):
    #logger.warning('Update "%s" caused error "%s"', update, context.error)
    logger.exception(context.error)
    # context.bot.send_message(chat_id=update.effective_chat.id,
    #                          text=f"Error:\n\n`{context.error}`",
    #                          parse_mode=telegram.ParseMode.MARKDOWN_V2)


updater = Updater(token=TOKEN, use_context=True)
dispatcher = updater.dispatcher

dispatcher.add_handler(CommandHandler('start', start_command))
dispatcher.add_handler(CommandHandler('rank', rank_command))
dispatcher.add_handler(CommandHandler('delete', delete_command))
dispatcher.add_handler(CommandHandler('stats', stats_command))
dispatcher.add_handler(CommandHandler('last5', last5_command))
dispatcher.add_handler(CommandHandler('proc', proc_command))
dispatcher.add_handler(CallbackQueryHandler(rank_callback))
dispatcher.add_handler(InlineQueryHandler(search_handler))
dispatcher.add_error_handler(error_handler)

if ONLINE:
    #create and start a webhook, so that the bot can be put to sleep when not in use, if you are running on Heroku
    updater.start_webhook(listen="0.0.0.0", port=PORT, url_path=TOKEN, webhook_url=APP_PATH + TOKEN)
    #update the status to "up"
    so.update_status(True)
    updater.idle()
    #if we got here, the updater must have been closed
    #therefore, update the status to "down"
    so.update_status(False)
else:
    #start polling if you are running in local
    updater.start_polling()
