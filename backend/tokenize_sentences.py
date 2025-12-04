from __future__ import annotations

from pathlib import Path

from app.services.checklists import _tokenize_document  # type: ignore

# Sample text to tokenize; edit as needed.
TEXT = """Filed: 2025-02-26
Court: District of District of Columbia
Source: RECAP
Status: Coding Complete

Case 1:25-cv-00385-ABJ     Document 27     Filed 02/26/25     Page 1 of 5
UNITED STATES DISTRICT COURT 
FOR THE DISTRICT OF COLUMBIA 
____________________________________ 
) 
HAMPTON DELLINGER  ) 
in his personal capacity and   ) 
in his official capacity as   ) 
Special Counsel of the   ) 
Office of Special Counsel,  ) 
) 
Plaintiff,  ) 
)  Civil Action No. 25-0385 (ABJ) 
v.  )   
) 
SCOTT BESSENT  ) 
in his official capacity as   ) 
Secretary of the Treasury, et al.,  ) 
) 
Defendants.  ) 
____________________________________) 
 
ORDER 
As of Friday, February 7, 2025, at 7:21 p.m., plaintiff Hampton Dellinger was the Special 
Counsel of the Office of Special Counsel, having been appointed by the President and confirmed 
by the Senate.  At 7:22 p.m., Sergio N. Gor, identified as an Assistant to the President, Director of 
Presidential  Personnel  Office,  informed  plaintiff  that  his  position  was  terminated  without 
identifying any reason.  Ex. A to Compl. [Dkt. # 1-1] at 1.   
On Monday, February 10, 2025, plaintiff sued to challenge the purported termination, and 
he moved for a temporary restraining order.  See Compl. [Dkt. # 1]; Pl.’s Mot. for a Temporary 
Restraining Order [Dkt. # 2] (“Pl.’s TRO”).  On that date, the Court entered a short administrative 
stay preserving the status quo while the parties briefed the matter, citing authority defining “status 
quo” as “‘the regime in place’ before the challenged action . . . or ‘the last uncontested status which 
preceded the pending controversy.’”  See Minute Order (Feb. 10, 2025), quoting Huisha-Huisha 
v. Mayorkas, 27 F.4th 718, 733–34 (D.C. Cir. 2022) and District 50, United Mine Workers of Am. 

Case 1:25-cv-00385-ABJ     Document 27     Filed 02/26/25     Page 2 of 5
v. Int’l Union, United Mine Workers of Am., 412 F.2d 165, 168 (D.C. Cir. 1969).  Defendants filed 
their opposition to the temporary restraining order the next day, February 11. See Defs.’ Opp. to 
Pl.’s TRO [Dkt. # 11].   
On February 12, 2025, the Court issued a temporary restraining order.  See Order [Dkt. 
# 14].  It was entered with notice to the opposing party, and it stated that it would remain in force 
until the Court ruled on plaintiff’s request for preliminary injunction.  See id. at 26 (“[F]rom the 
date of entry of this order until the Court rules on the entry of preliminary injunction, plaintiff 
Hampton Dellinger shall continue to serve as Special Counsel . . . .”).  The Court scheduled the 
preliminary injunction hearing for a date 14 days later:  February 26.  Id. at 27.   Given the terms 
of Federal Rule of Civil Procedure 65 and the understandings expressed by the Supreme Court and 
the Court of Appeals, the temporary restraining order expires today. 
When the TRO was issued on February 12, plaintiff had not yet had the opportunity to 
reply to the defendants’ opposition, so the Court established a briefing schedule.  It also directed 
the parties to inform the Court of their positions as to whether the Court should advance the 
consideration of the merits and consolidate it with the preliminary injunction hearing under Rule 
of Civil Procedure 65(a)(2) by February 14, 2025.  Id. at 26–27.   
  In the meantime, on February 12, defendants noticed an appeal of the temporary restraining 
order.  See Defs.’ Notice of Appeal [Dkt. # 15].   
On February 14, the Court received a joint status report from the parties with their positions 
on consolidation:  plaintiff deferred to the Court, and defendants stated their preference for 
utilizing the procedure that would result in the prompt issuance of a decision on the merits.  See 
Joint Status Report [Dkt. # 20] at 1–2.  Based on that submission, the Court entered an order 
 
consolidating  the  preliminary  injunction  with  the  merits,  and  it  called  for  the  expeditious 
2 
 

Case 1:25-cv-00385-ABJ     Document 27     Filed 02/26/25     Page 3 of 5
submission of cross motions for summary judgment, culminating with the hearing today and the 
final reply being filed tomorrow.  See Minute Order (Feb. 15, 2025).  It also informed the parties 
that they had the option of incorporating or relying upon previously filed memoranda in support 
of those motions.  Id.   
On February 15, 2025, the Court of Appeals dismissed defendants’ appeal for lack of 
jurisdiction since the temporary restraining order was not a final order.  See Order, Dellinger v. 
Bessent, 25-5028 (Feb. 15, 2025).  On February 16, defendants filed an application with the 
Supreme Court seeking immediate review of the temporary restraining order.  See Appl. to Vacate 
the Order, Bessent v. Dellinger, No. 24A (Feb. 16, 2025).  On February 20, plaintiff filed his reply 
to the opposition to the motion for interim relief, raising some arguments that had not been 
advanced in the initial motion.            
  On Friday, February 21, 2025, five days after the application was filed, the Supreme Court 
announced that it would hold the application in abeyance for the remainder of the fourteen days 
until the temporary restraining order was due to expire, that is, until Feb 26, the date of the hearing.  
Bessent v. Dellinger, 604 U.S. __ (2025).   
  Under Federal Rule of Civil Procedure 65(b)(2), a temporary restraining order without 
notice is valid for a period “not to exceed 14 days . . . unless before that time the court, for good 
cause, extends it for a like period or the adverse party consents to a longer extension.”  Fed. R. 
Civ. P. 65(b)(2).  While Rule 65(b)(2) is silent on the timeline for temporary restraining orders 
entered with notice, it is generally accepted that the standard  fourteen days followed by a 
fourteen-day extension for good cause applies to a TRO entered with notice as well.  See 11A 
 
Charles A. Wright, Federal Practice & Procedure § 2953 (3d ed. 2024) (“The text of Rule 65(b) 
seems to exclude any possibility that a temporary restraining order can remain in force beyond 28 
3 
 

Case 1:25-cv-00385-ABJ     Document 27     Filed 02/26/25     Page 4 of 5
days. . . .  It also has been held that this time limitation applies even when the order is not issued 
ex parte and both notice and a hearing are held.”).  If a TRO lasts longer than twenty-eight days, 
courts will construe it to be a preliminary injunction, which would be appealable immediately.  Id.; 
see Nat’l Mediation Bd. v. Airline Pilots Ass’n, Int’l, 323 F.2d 305, 305 (D.C. Cir. 1963).  
The Court is well aware that the case is in the very unusual posture of being the subject of 
an application before the Supreme Court before a final order has been issued and before the United 
States Court of Appeals for the District Columbia has had the opportunity to review that final 
order.  It recognizes that the Supreme Court – with the understanding that the TRO expires at 
midnight tonight – is holding the application in abeyance until that time.  So it is incumbent upon 
this Court to resolve this matter even more expeditiously than the Federal Rules of Civil Procedure 
would ordinarily permit; and the Court will do so.   
Given  the  significance  of  the  constitutional  questions  presented,  though,  it  is  also 
incumbent upon the Court to give full consideration to all of the arguments advanced during 
today’s hearing before it finalizes its opinion.  It is also necessary to give close consideration to 
all of the pleadings submitted by the parties after the TRO issued, and to rule on questions raised 
after the defendants asked the Supreme Court to take the case. This includes defendants’ thirty-
page motion for summary judgment [Dkt. 22], filed on Friday, February 21, which advances 
arguments concerning the Court’s authority to impose equitable remedies for the first time before 
this Court; plaintiff’s forty-page opposition and cross motion for summary judgment, filed on 
Monday, February 24; defendants’ reply, filed on February 25; and plaintiff’s cross opposition, 
which is not due until tomorrow.  This is particularly true now that the motion for a preliminary 
injunction has been consolidated with the merits, as defendants requested.   
4 
 

Case 1:25-cv-00385-ABJ     Document 27     Filed 02/26/25     Page 5 of 5
At the hearing, the Court solicited the parties’ views on the matter.  Plaintiff agrees that a 
short extension in accordance with the Federal Rules would be appropriate to facilitate full 
consideration of the positions of the parties and the arguments made at the hearing.  He also noted 
that once the Court ruled on the merits in a final, appealable order, the TRO would be vacated, and 
the application would be moot.  While counsel for the defendants indicated a lack of familiarity 
with the relevant legislative history and proposed to look into it as the subject of a supplemental 
filing, she voiced defendants’ objection to any extension of the TRO for the same reasons they 
opposed it in the first place.  
In consideration of all of these circumstances, then, the Court finds, pursuant to Rule 
65(b)(2), that there is good cause to extend the temporary restraining order for an additional three 
days, through Saturday, March 1, so that the status quo will be preserved for the brief period of 
time it takes to complete the written opinion on the consolidated motion for preliminary injunction 
and cross motions for summary judgment.   
SO ORDERED. 
 
AMY BERMAN JACKSON 
United States District Judge 
 
DATE:  February 26, 2025 
5

Clearinghouse file: https://clearinghouse-umich-production.s3.amazonaws.com/media/doc/156284.pdf
External link: https://www.courtlistener.com/docket/69624836/27/dellinger-v-bessent/
Clearinghouse summary: clearinghouse.net/doc/156284"""


def main() -> None:
    payload = {"id": 1, "title": "Example", "type": "Demo", "text": TEXT}
    tokenized = _tokenize_document(payload)

    print(f"Document: {tokenized.title} (id={tokenized.document_id})")
    print(f"Truncated: {tokenized.truncated}")
    print()
    for sentence in tokenized.sentences:
        print(f"Sentence {sentence.sentence_id}: [{sentence.start}, {sentence.end}) {sentence.text!r}")


if __name__ == "__main__":
    # Allow running from project root or scratch/
    import sys

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    main()
