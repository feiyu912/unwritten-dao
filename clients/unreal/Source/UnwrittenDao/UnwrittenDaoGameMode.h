// Copyright Unwritten Dao. All Rights Reserved.
// scaffold: place to assign Blueprint HUD/widget classes in the editor. Gameplay rules stay
// on the server; this GameMode only hosts presentation and the local player controller.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "UnwrittenDaoGameMode.generated.h"

UCLASS()
class UNWRITTENDAO_API AUnwrittenDaoGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	AUnwrittenDaoGameMode();
};